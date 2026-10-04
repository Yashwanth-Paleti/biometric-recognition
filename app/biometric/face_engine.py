from pathlib import Path
from typing import Any, Union
import warnings
import cv2
import numpy as np

from app.biometric.embedding import validate_embedding
from app.biometric.exceptions import (
    BiometricEngineError,
    EmbeddingExtractionError,
    InvalidImageError,
    ModelInitializationError,
    MultipleFacesDetectedError,
    NoFaceDetectedError,
)
from app.config.settings import settings
from app.utils.logging import logger

# Suppress harmless future warnings from insightface internal libraries
warnings.filterwarnings("ignore", category=FutureWarning)


class FaceEngine:
    """
    Encapsulated face detection and embedding extraction engine.
    Wraps InsightFace / ONNX Runtime execution details behind a clean abstraction.
    """

    def __init__(self):
        self._app: Any = None
        self._initialized: bool = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def initialize(self) -> None:
        """
        Initializes the InsightFace FaceAnalysis pipeline.
        Idempotent: will not reinitialize if already initialized.
        """
        if self._initialized and self._app is not None:
            return

        try:
            from insightface.app import FaceAnalysis

            logger.info(
                f"Initializing FaceEngine with model: {settings.model_name}, "
                f"provider: {settings.execution_provider}"
            )
            self._app = FaceAnalysis(
                name=settings.model_name,
                providers=[settings.execution_provider]
            )
            self._app.prepare(ctx_id=0, det_size=settings.det_size)
            self._initialized = True
            logger.info("FaceEngine successfully initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize FaceEngine: {e}")
            raise ModelInitializationError(f"Engine initialization failed: {e}")

    def _ensure_initialized(self) -> None:
        if not self._initialized or self._app is None:
            self.initialize()

    def process_image(self, image_input: Union[str, Path, bytes, np.ndarray]) -> np.ndarray:
        """
        Loads and validates an image from multiple input types:
        - File path (str or Path)
        - Raw encoded bytes (e.g. from an upload or network payload)
        - Pre-decoded numpy ndarray (e.g. from cv2 VideoCapture)

        Returns an RGB numpy ndarray ready for inference.
        """
        if image_input is None:
            logger.warning("process_image received None input.")
            raise InvalidImageError("Image input cannot be None.")

        image_bgr: np.ndarray | None = None

        if isinstance(image_input, (str, Path)):
            path = Path(image_input)
            if not path.is_file():
                logger.warning(f"Image file not found: {path}")
                raise InvalidImageError(f"Image file not found: {path}")
            image_bgr = cv2.imread(str(path))
            if image_bgr is None:
                raise InvalidImageError(f"Failed to decode image from path: {path}")

        elif isinstance(image_input, bytes):
            if len(image_input) == 0:
                raise InvalidImageError("Image byte stream is empty.")
            nparr = np.frombuffer(image_input, np.uint8)
            image_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if image_bgr is None:
                raise InvalidImageError("Failed to decode image from byte buffer.")

        elif isinstance(image_input, np.ndarray):
            if image_input.size == 0:
                raise InvalidImageError("Input image numpy array is empty.")
            # If already provided as numpy array, check channels
            if image_input.ndim == 2:  # Grayscale
                image_bgr = cv2.cvtColor(image_input, cv2.COLOR_GRAY2BGR)
            elif image_input.ndim == 3:
                image_bgr = image_input
            else:
                raise InvalidImageError(f"Unexpected image array shape: {image_input.shape}")
        else:
            raise InvalidImageError(f"Unsupported image input type: {type(image_input)}")

        if image_bgr is None or image_bgr.size == 0:
            raise InvalidImageError("Processed image contains no valid pixel data.")

        # InsightFace expects RGB format
        rgb_image = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        return rgb_image

    def detect_faces(self, image: np.ndarray) -> list[Any]:
        """
        Executes face detection on an RGB image.
        Returns a list of InsightFace Face objects.
        """
        self._ensure_initialized()
        try:
            faces = self._app.get(image)
            logger.debug(f"Detected {len(faces)} face(s) in frame.")
            return faces
        except Exception as e:
            logger.error(f"Error during face detection: {e}")
            raise BiometricEngineError(f"Face detection failure: {e}")

    def generate_embedding(self, face: Any) -> np.ndarray:
        """
        Extracts and validates a 512-dimensional normalized embedding from a detected Face object.
        """
        if face is None:
            raise EmbeddingExtractionError("Face object cannot be None.")

        embedding = getattr(face, "normed_embedding", None)
        if embedding is None:
            embedding = getattr(face, "embedding", None)

        if embedding is None:
            raise EmbeddingExtractionError("No embedding vector found on detected face object.")

        return validate_embedding(embedding)

    def generate_embedding_from_image(
        self,
        image_input: Union[str, Path, bytes, np.ndarray],
        require_single_face: bool = True
    ) -> np.ndarray:
        """
        Convenience pipeline: processes image -> detects faces -> validates constraints -> extracts embedding.

        Raises:
            InvalidImageError: If image is corrupted or missing.
            NoFaceDetectedError: If no face is detected.
            MultipleFacesDetectedError: If require_single_face is True and >1 face detected.
            EmbeddingExtractionError: If feature extraction fails.
        """
        rgb_image = self.process_image(image_input)
        faces = self.detect_faces(rgb_image)

        if len(faces) == 0:
            logger.info("Face detection returned 0 faces.")
            raise NoFaceDetectedError()

        if require_single_face and len(faces) > 1:
            logger.warning(f"Multiple faces ({len(faces)}) detected when single face was required.")
            raise MultipleFacesDetectedError(
                f"Detected {len(faces)} faces. Exactly 1 face is required for this operation."
            )

        # In multi-face mode (if require_single_face=False), choose the primary/largest face
        primary_face = faces[0]
        if len(faces) > 1:
            # Sort by bounding box area (largest face in foreground)
            def box_area(f: Any) -> float:
                bbox = getattr(f, "bbox", [0, 0, 0, 0])
                return (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            primary_face = max(faces, key=box_area)

        embedding = self.generate_embedding(primary_face)
        logger.debug("Successfully generated 512-d biometric embedding.")
        return embedding
