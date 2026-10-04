import json
import os
from pathlib import Path
import pickle
import threading
from typing import Optional
import numpy as np

from app.biometric.matching import FaceMatcher
from app.config.settings import settings
from app.models.biometric import BiometricTemplate, User
from app.storage.base import BiometricRepository
from app.utils.logging import logger


class LocalBiometricRepository(BiometricRepository):
    """
    Local JSON-based repository implementation for Stage 1.
    Keeps persistence behind the BiometricRepository interface so that Stage 2
    can replace this with PostgreSQL + pgvector without modifying service logic.
    """

    def __init__(
        self,
        storage_path: Optional[Path] = None,
        auto_import_legacy: bool = True
    ):
        self.storage_path = (
            Path(storage_path) if storage_path else settings.local_storage_path
        )
        self.legacy_pickle_path = settings.legacy_pickle_path
        self._lock = threading.Lock()
        self._templates: dict[str, BiometricTemplate] = {}
        self._users: dict[str, User] = {}
        self._logs: list[dict] = []
        self._matcher = FaceMatcher()
        
        # Ensure parent directory exists
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._load()
        
        if auto_import_legacy and len(self._templates) == 0:
            self._import_from_legacy_pickle()

    def _load(self) -> None:
        """Loads templates from JSON file into in-memory dictionary."""
        with self._lock:
            if not self.storage_path.exists():
                self._templates = {}
                return

            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._templates = {
                    item["template_id"]: BiometricTemplate.from_dict(item)
                    for item in data.get("templates", [])
                }
                logger.info(
                    f"Loaded {len(self._templates)} biometric template(s) from {self.storage_path}"
                )
            except Exception as e:
                logger.error(f"Failed to read templates from {self.storage_path}: {e}")
                self._templates = {}

    def _save(self) -> None:
        """Persists in-memory templates to JSON file atomically."""
        data = {
            "version": "1.0",
            "count": len(self._templates),
            "templates": [t.to_dict() for t in self._templates.values()],
        }
        temp_path = self.storage_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            temp_path.replace(self.storage_path)
            logger.debug(f"Saved {len(self._templates)} template(s) to {self.storage_path}")
        except Exception as e:
            logger.error(f"Failed to write templates to {self.storage_path}: {e}")
            if temp_path.exists():
                temp_path.unlink()
            raise

    def _import_from_legacy_pickle(self) -> None:
        """
        Backward-compatibility loader:
        Imports legacy student encodings from 'encodings/face_encodings.pickle'
        if the local template database is newly initialized.
        """
        if not self.legacy_pickle_path.exists():
            return

        try:
            logger.info(f"Importing legacy encodings from {self.legacy_pickle_path}...")
            with open(self.legacy_pickle_path, "rb") as f:
                legacy_data = pickle.load(f)

            encodings = legacy_data.get("encodings", [])
            metadata = legacy_data.get("metadata", [])

            imported_count = 0
            with self._lock:
                for enc, meta in zip(encodings, metadata):
                    user_id = str(meta.get("roll_no", meta.get("name", "legacy_user")))
                    # Clean up roll number e.g. "1.0" -> "01000" or raw string
                    template = BiometricTemplate(
                        user_id=user_id,
                        embedding=np.array(enc, dtype=np.float32),
                        model_name="buffalo_l",
                        model_version="legacy",
                        metadata={
                            "name": meta.get("name", "Unknown"),
                            "branch": meta.get("branch", ""),
                            "semester": meta.get("semester", ""),
                            "section": meta.get("section", ""),
                            "source": "legacy_pickle_import",
                        }
                    )
                    self._templates[template.template_id] = template
                    imported_count += 1

                self._save()

            logger.info(f"Successfully migrated {imported_count} legacy biometric templates.")
        except Exception as e:
            logger.warning(f"Could not import legacy pickle file: {e}")

    def save_template(self, template: BiometricTemplate) -> bool:
        with self._lock:
            self._templates[template.template_id] = template
            self._save()
            return True

    def get_templates(self, user_id: str) -> list[BiometricTemplate]:
        with self._lock:
            return [
                t for t in self._templates.values()
                if t.user_id == user_id and t.status == "active"
            ]

    def get_template_by_id(self, template_id: str) -> Optional[BiometricTemplate]:
        with self._lock:
            template = self._templates.get(template_id)
            if template and template.status == "active":
                return template
            return None

    def get_all_templates(self) -> list[BiometricTemplate]:
        with self._lock:
            return [t for t in self._templates.values() if t.status == "active"]

    def delete_template(self, template_id: str) -> bool:
        with self._lock:
            if template_id in self._templates:
                del self._templates[template_id]
                self._save()
                return True
            return False

    def delete_templates_by_user(self, user_id: str) -> int:
        with self._lock:
            to_delete = [
                tid for tid, t in self._templates.items()
                if t.user_id == user_id
            ]
            for tid in to_delete:
                del self._templates[tid]
            if to_delete:
                self._save()
            return len(to_delete)

    def count(self) -> int:
        with self._lock:
            return sum(1 for t in self._templates.values() if t.status == "active")

    def get_user(self, user_id: str) -> Optional[User]:
        """Retrieves user domain entity by user_id."""
        with self._lock:
            if user_id in self._users:
                return self._users[user_id]
            matching = [t for t in self._templates.values() if t.user_id == user_id]
            if matching:
                name = matching[0].metadata.get("name", user_id)
                return User(user_id=user_id, name=name)
            return None

    def save_user(self, user: User) -> bool:
        """Saves user domain entity."""
        with self._lock:
            self._users[user.user_id] = user
            return True

    def log_authentication(
        self,
        user_id: Optional[str],
        verification_type: str,
        result: str,
        threshold: float,
        similarity: Optional[float] = None,
        distance: Optional[float] = None,
        error_code: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> bool:
        """Records an authentication attempt in local audit log."""
        with self._lock:
            self._logs.append({
                "user_id": user_id,
                "verification_type": verification_type,
                "result": result,
                "threshold": threshold,
                "similarity": similarity,
                "distance": distance,
                "error_code": error_code,
                "device_id": device_id,
            })
            return True

    def find_nearest_template(
        self,
        query_embedding: np.ndarray,
        threshold: Optional[float] = None,
    ) -> tuple[Optional[BiometricTemplate], Optional[float], Optional[float]]:
        """1:N matching across local active templates."""
        candidates = self.get_all_templates()
        if not candidates:
            return None, None, None
        return self._matcher.find_best_match(query_embedding, candidates, threshold=threshold)

