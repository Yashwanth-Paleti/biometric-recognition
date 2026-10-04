from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check endpoint response payload."""
    status: str = Field(default="healthy", description="Current service health status")
    version: str = Field(default="2.0.0", description="API and backend architecture version")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Current server timestamp (UTC)",
    )
    storage_backend: str = Field(
        default="local",
        description="Active biometric storage repository ('local' or 'postgres')",
    )
    database_connected: Optional[bool] = Field(
        default=None,
        description="True if PostgreSQL database connection is verified and healthy",
    )


class EnrollmentResponse(BaseModel):
    """
    Standardized response payload for biometric enrollment.
    Strictly excludes raw embeddings or biometric vector features.
    """
    success: bool = Field(default=True, description="Indicates whether enrollment succeeded")
    user_id: str = Field(description="Unique user identifier enrolled into system")
    message: str = Field(
        default="Biometric enrollment successful",
        description="Human-readable result summary",
    )
    template_id: Optional[str] = Field(
        default=None,
        description="Unique UUID of the enrolled biometric template",
    )


class VerificationResponse(BaseModel):
    """
    Standardized response payload for 1:1 biometric verification.
    Strictly excludes raw embeddings or face captures.
    """
    authenticated: bool = Field(
        description="True if probe biometric matches claimed identity within threshold"
    )
    user_id: str = Field(description="Claimed user identifier evaluated")
    similarity: Optional[float] = Field(
        default=None,
        description="Calculated cosine similarity score between probe and enrolled template ([-1.0, 1.0])",
    )
    distance: Optional[float] = Field(
        default=None,
        description="Calculated Euclidean (L2) distance between embeddings",
    )
    message: str = Field(description="Human-readable verification decision description")


class IdentificationResponse(BaseModel):
    """
    Standardized response payload for 1:N biometric identification.
    Strictly excludes raw embeddings or face captures.
    """
    authenticated: bool = Field(
        description="True if probe matches an enrolled template within threshold"
    )
    user_id: Optional[str] = Field(
        default=None,
        description="Matched user identifier, or null if unauthenticated / unknown",
    )
    similarity: Optional[float] = Field(
        default=None,
        description="Cosine similarity of best matching candidate in gallery",
    )
    distance: Optional[float] = Field(
        default=None,
        description="Euclidean distance of best matching candidate in gallery",
    )
    message: str = Field(description="Human-readable identification decision summary")


class ErrorResponse(BaseModel):
    """Structured error contract returned across API endpoints."""
    detail: str = Field(description="Descriptive explanation of the error")
    error_code: Optional[str] = Field(
        default=None,
        description="Machine-readable domain error code (e.g. NO_FACE_DETECTED)",
    )
