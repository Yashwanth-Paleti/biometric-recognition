from app.biometric.exceptions import (
    BiometricError,
    BiometricEngineError,
    NoFaceDetectedError,
    MultipleFacesDetectedError,
    InvalidImageError,
    EmbeddingExtractionError,
    ModelInitializationError,
)
from app.biometric.embedding import validate_embedding, create_face_embedding
from app.biometric.face_engine import FaceEngine
from app.biometric.matching import FaceMatcher

__all__ = [
    "BiometricError",
    "BiometricEngineError",
    "NoFaceDetectedError",
    "MultipleFacesDetectedError",
    "InvalidImageError",
    "EmbeddingExtractionError",
    "ModelInitializationError",
    "validate_embedding",
    "create_face_embedding",
    "FaceEngine",
    "FaceMatcher",
]
