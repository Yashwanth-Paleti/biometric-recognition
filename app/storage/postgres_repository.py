import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Tuple, Union
import numpy as np
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.biometric.embedding import validate_embedding
from app.biometric.exceptions import EmbeddingExtractionError
from app.database.connection import get_session_factory, session_scope
from app.database.models import (
    AuthenticationLogModel,
    BiometricTemplateModel,
    UserModel,
)
from app.models.biometric import BiometricTemplate, User
from app.storage.base import BiometricRepository
from app.utils.logging import logger


class PostgresBiometricRepository(BiometricRepository):
    """
    PostgreSQL + pgvector implementation of the BiometricRepository interface.
    Persists 512-dimensional facial embeddings and performs database-native vector
    similarity search using pgvector's Euclidean (L2) distance operator (<->).
    """

    def __init__(self, session_factory: Optional[sessionmaker] = None):
        self._session_factory = session_factory

    @property
    def session_factory(self) -> sessionmaker:
        if self._session_factory is None:
            self._session_factory = get_session_factory()
        return self._session_factory

    def _validate_and_sanitize_vector(
        self, embedding: Union[np.ndarray, list[float]]
    ) -> list[float]:
        """
        Validates embedding dimensions (512), finite float representation,
        and converts it into a pgvector-compatible float list.
        """
        validated_arr = validate_embedding(embedding)
        return validated_arr.astype(float).tolist()


    def get_user(self, user_id: str) -> Optional[User]:
        """Retrieves a user domain entity by user_id."""
        with session_scope(self.session_factory) as session:
            stmt = select(UserModel).where(UserModel.user_id == user_id)
            user_model = session.execute(stmt).scalar_one_or_none()
            if not user_model:
                return None
            return User(
                user_id=user_model.user_id,
                name=user_model.name,
                metadata={"email": user_model.email, "status": user_model.status},
                created_at=(
                    user_model.created_at.isoformat()
                    if user_model.created_at
                    else ""
                ),
            )

    def save_user(self, user: User) -> bool:
        """Creates or updates a user record."""
        with session_scope(self.session_factory) as session:
            stmt = select(UserModel).where(UserModel.user_id == user.user_id)
            user_model = session.execute(stmt).scalar_one_or_none()

            email = user.metadata.get("email") if user.metadata else None
            status = user.metadata.get("status", "active") if user.metadata else "active"

            if user_model is None:
                user_model = UserModel(
                    user_id=user.user_id,
                    name=user.name,
                    email=email,
                    status=status,
                )
                session.add(user_model)
            else:
                user_model.name = user.name
                if email is not None:
                    user_model.email = email
                user_model.status = status
            return True

    def save_template(self, template: BiometricTemplate) -> bool:
        """
        Persists a biometric template into PostgreSQL.
        Ensures foreign key constraint by creating a user record if one does not already exist.
        """
        vector_list = self._validate_and_sanitize_vector(template.embedding)

        with session_scope(self.session_factory) as session:
            # Guarantee user exists for foreign key constraint
            stmt_user = select(UserModel).where(UserModel.user_id == template.user_id)
            user_model = session.execute(stmt_user).scalar_one_or_none()
            if user_model is None:
                display_name = (
                    template.metadata.get("name", template.user_id)
                    if template.metadata
                    else template.user_id
                )
                user_model = UserModel(
                    user_id=template.user_id,
                    name=display_name,
                    status="active",
                )
                session.add(user_model)
                session.flush()

            # Check if template with template_id exists
            stmt_tmpl = select(BiometricTemplateModel).where(
                BiometricTemplateModel.id == template.template_id
            )
            tmpl_model = session.execute(stmt_tmpl).scalar_one_or_none()

            if tmpl_model is None:
                tmpl_model = BiometricTemplateModel(
                    id=template.template_id,
                    user_id=template.user_id,
                    embedding=vector_list,
                    model_name=template.model_name,
                    model_version=template.model_version,
                    status=template.status,
                    metadata_json=template.metadata or {},
                )
                session.add(tmpl_model)
            else:
                tmpl_model.embedding = vector_list
                tmpl_model.model_name = template.model_name
                tmpl_model.model_version = template.model_version
                tmpl_model.status = template.status
                tmpl_model.metadata_json = template.metadata or {}

            logger.debug(
                f"Saved template {template.template_id} for user {template.user_id} in PostgreSQL."
            )
            return True

    def get_templates(self, user_id: str) -> list[BiometricTemplate]:
        """Retrieves all active templates for a specific user."""
        with session_scope(self.session_factory) as session:
            stmt = select(BiometricTemplateModel).where(
                BiometricTemplateModel.user_id == user_id,
                BiometricTemplateModel.status == "active",
            )
            models = session.execute(stmt).scalars().all()
            return [self._to_domain_template(m) for m in models]

    def get_template_by_id(self, template_id: str) -> Optional[BiometricTemplate]:
        """Retrieves a single active template by its unique template_id."""
        with session_scope(self.session_factory) as session:
            stmt = select(BiometricTemplateModel).where(
                BiometricTemplateModel.id == template_id,
                BiometricTemplateModel.status == "active",
            )
            model = session.execute(stmt).scalar_one_or_none()
            return self._to_domain_template(model) if model else None

    def get_all_templates(self) -> list[BiometricTemplate]:
        """Retrieves all active biometric templates in the database."""
        with session_scope(self.session_factory) as session:
            stmt = select(BiometricTemplateModel).where(
                BiometricTemplateModel.status == "active"
            )
            models = session.execute(stmt).scalars().all()
            return [self._to_domain_template(m) for m in models]

    def delete_template(self, template_id: str) -> bool:
        """Deletes a template by its template_id."""
        with session_scope(self.session_factory) as session:
            stmt = delete(BiometricTemplateModel).where(
                BiometricTemplateModel.id == template_id
            )
            res = session.execute(stmt)
            return res.rowcount > 0

    def delete_templates_by_user(self, user_id: str) -> int:
        """Deletes all templates belonging to a specific user. Returns count deleted."""
        with session_scope(self.session_factory) as session:
            stmt = delete(BiometricTemplateModel).where(
                BiometricTemplateModel.user_id == user_id
            )
            res = session.execute(stmt)
            return int(res.rowcount)

    def count(self) -> int:
        """Returns the total number of active biometric templates."""
        with session_scope(self.session_factory) as session:
            stmt = (
                select(func.count(BiometricTemplateModel.id))
                .where(BiometricTemplateModel.status == "active")
            )
            return int(session.execute(stmt).scalar() or 0)

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
        """
        Records an audit entry into authentication_logs table.
        Strictly excludes facial images, passwords, tokens, or raw embeddings.
        """
        try:
            with session_scope(self.session_factory) as session:
                log_entry = AuthenticationLogModel(
                    user_id=user_id,
                    verification_type=verification_type,
                    result=result,
                    threshold=float(threshold),
                    similarity=float(similarity) if similarity is not None else None,
                    distance=float(distance) if distance is not None else None,
                    error_code=error_code,
                    device_id=device_id,
                )
                session.add(log_entry)
                return True
        except Exception as e:
            logger.error(f"Failed to record authentication audit log: {e}")
            return False

    def find_nearest_template(
        self,
        query_embedding: np.ndarray,
        threshold: Optional[float] = None,
    ) -> Tuple[Optional[BiometricTemplate], Optional[float], Optional[float]]:
        """
        Performs database-native 1:N vector similarity search using pgvector.
        
        Metric Rationale:
        InsightFace Buffalo_L generates 512-dimensional vectors normalized to the unit sphere (L2 norm = 1.0).
        For normalized vectors:
            L2_distance^2 = 2 - 2 * Cosine_Similarity
        pgvector's Euclidean distance operator (<->) directly calculates L2 distance,
        leveraging the HNSW index (vector_l2_ops) for hardware-accelerated nearest-neighbor search.
        
        Returns:
            (best_template, similarity_score, distance)
            If distance exceeds threshold, returns (None, similarity_score, distance).
            If no candidates exist, returns (None, None, None).
        """
        vector_list = self._validate_and_sanitize_vector(query_embedding)

        with session_scope(self.session_factory) as session:
            # Query pgvector for the closest active template using Euclidean (<->) distance
            distance_expr = BiometricTemplateModel.embedding.l2_distance(vector_list)
            stmt = (
                select(BiometricTemplateModel, distance_expr.label("distance"))
                .where(BiometricTemplateModel.status == "active")
                .order_by(distance_expr.asc())
                .limit(1)
            )

            result = session.execute(stmt).first()
            if result is None:
                return None, None, None

            tmpl_model, dist_val = result
            dist_float = float(dist_val)

            # Cosine similarity for unit vectors: sim = 1.0 - (d^2) / 2.0
            sim_float = float(np.clip(1.0 - (dist_float ** 2) / 2.0, -1.0, 1.0))
            best_template = self._to_domain_template(tmpl_model)

            if threshold is not None and dist_float > threshold:
                # Match threshold not satisfied
                return None, sim_float, dist_float

            return best_template, sim_float, dist_float

    def _to_domain_template(
        self, model: BiometricTemplateModel
    ) -> BiometricTemplate:
        """Converts an ORM BiometricTemplateModel to domain BiometricTemplate."""
        emb_arr = np.array(model.embedding, dtype=np.float32)
        return BiometricTemplate(
            template_id=str(model.id),
            user_id=str(model.user_id),
            embedding=emb_arr,
            model_name=str(model.model_name),
            model_version=str(model.model_version),
            status=str(model.status),
            metadata=dict(model.metadata_json or {}),
            created_at=(
                model.created_at.isoformat()
                if model.created_at
                else datetime.now(timezone.utc).isoformat()
            ),
        )
