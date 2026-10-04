class BiometricError(Exception):
    """Base exception for all biometric core operations."""
    def __init__(self, message: str, error_code: str = "BIOMETRIC_ERROR"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code

BiometricEngineError = BiometricError


class NoFaceDetectedError(BiometricError):
    """Raised when face detection algorithm detects zero faces in an image."""
    def __init__(self, message: str = "No face detected in the provided image."):
        super().__init__(message, error_code="NO_FACE_DETECTED")


class MultipleFacesDetectedError(BiometricError):
    """Raised when more than one face is detected during single-subject operation."""
    def __init__(self, message: str = "Multiple faces detected. Exactly one face is required for this operation."):
        super().__init__(message, error_code="MULTIPLE_FACES_DETECTED")


class InvalidImageError(BiometricError):
    """Raised when the provided image cannot be decoded, is empty, or is corrupted."""
    def __init__(self, message: str = "Invalid or corrupted image input."):
        super().__init__(message, error_code="INVALID_IMAGE")


class EmbeddingExtractionError(BiometricError):
    """Raised when feature extraction fails on a detected face."""
    def __init__(self, message: str = "Failed to extract biometric embedding from face."):
        super().__init__(message, error_code="EMBEDDING_EXTRACTION_FAILED")


class ModelInitializationError(BiometricError):
    """Raised when the deep learning inference engine fails to initialize."""
    def __init__(self, message: str = "Failed to initialize biometric model."):
        super().__init__(message, error_code="MODEL_INIT_FAILED")
