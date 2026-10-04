from app.biometric.exceptions import (
    BiometricError,
    BiometricEngineError,
    NoFaceDetectedError,
    MultipleFacesDetectedError,
    InvalidImageError,
    EmbeddingExtractionError,
    ModelInitializationError,
    LivenessCheckFailedError,
)
from app.biometric.embedding import validate_embedding, create_face_embedding
from app.biometric.face_engine import FaceEngine
from app.biometric.matching import FaceMatcher
from app.biometric.liveness import (
    BaseLivenessDetector,
    LivenessResult,
    PassiveTextureFrequencyLivenessDetector,
    PassThroughLivenessDetector,
    get_liveness_detector,
)

__all__ = [
    "BiometricError",
    "BiometricEngineError",
    "NoFaceDetectedError",
    "MultipleFacesDetectedError",
    "InvalidImageError",
    "EmbeddingExtractionError",
    "ModelInitializationError",
    "LivenessCheckFailedError",
    "validate_embedding",
    "create_face_embedding",
    "FaceEngine",
    "FaceMatcher",
    "BaseLivenessDetector",
    "LivenessResult",
    "PassiveTextureFrequencyLivenessDetector",
    "PassThroughLivenessDetector",
    "get_liveness_detector",
]

