from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
import uuid
import numpy as np


@dataclass
class User:
    """Represents an authenticated user within the biometric system."""
    user_id: str
    name: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class FaceEmbedding:
    """Encapsulates a normalized 512-dimensional facial embedding vector and detection metadata."""
    vector: np.ndarray
    dimension: int = 512
    bbox: Optional[list[int]] = None
    detection_score: Optional[float] = None

    def __post_init__(self):
        if not isinstance(self.vector, np.ndarray):
            self.vector = np.array(self.vector, dtype=np.float32)
        if self.vector.ndim != 1:
            self.vector = self.vector.flatten()
        self.dimension = self.vector.shape[0]

    def to_list(self) -> list[float]:
        return self.vector.astype(float).tolist()


@dataclass
class BiometricTemplate:
    """
    Logical representation of an enrolled biometric template.
    Decoupled from specific database persistence layers.
    """
    user_id: str
    embedding: np.ndarray
    model_name: str = "buffalo_l"
    model_version: str = "1.0.0"
    template_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    status: str = "active"  # 'active', 'revoked', 'pending'
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.embedding, np.ndarray):
            self.embedding = np.array(self.embedding, dtype=np.float32)
        if self.embedding.ndim != 1:
            self.embedding = self.embedding.flatten()

    def to_dict(self) -> dict[str, Any]:
        """Convert template into a serializable dictionary representation."""
        return {
            "template_id": self.template_id,
            "user_id": self.user_id,
            "embedding": self.embedding.astype(float).tolist(),
            "model_name": self.model_name,
            "model_version": self.model_version,
            "created_at": self.created_at,
            "status": self.status,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BiometricTemplate":
        """Construct a BiometricTemplate instance from a dictionary."""
        return cls(
            template_id=data.get("template_id", str(uuid.uuid4())),
            user_id=data["user_id"],
            embedding=np.array(data["embedding"], dtype=np.float32),
            model_name=data.get("model_name", "buffalo_l"),
            model_version=data.get("model_version", "1.0.0"),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            status=data.get("status", "active"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class BiometricVerification:
    """Record of a 1:1 or 1:N comparison between query embedding and enrolled template."""
    query_user_id: Optional[str]
    matched_user_id: Optional[str]
    is_match: bool
    similarity_score: float
    distance: float
    threshold: float
    status: str  # 'MATCH', 'NO_MATCH', 'AMBIGUOUS'


@dataclass
class AuthenticationAttempt:
    """Audit log entry representing a biometric authentication event."""
    attempt_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    success: bool = False
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuthenticationResult:
    """
    Standardized result contract returned by the BiometricService.
    Conceals low-level engine details while providing complete decision status.
    """
    success: bool
    matched: bool
    user_id: Optional[str] = None
    similarity: Optional[float] = None
    distance: Optional[float] = None
    threshold: Optional[float] = None
    error_code: Optional[str] = None
    message: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "matched": self.matched,
            "user_id": self.user_id,
            "similarity": round(self.similarity, 4) if self.similarity is not None else None,
            "distance": round(self.distance, 4) if self.distance is not None else None,
            "threshold": self.threshold,
            "error_code": self.error_code,
            "message": self.message,
            "metadata": self.metadata,
        }
