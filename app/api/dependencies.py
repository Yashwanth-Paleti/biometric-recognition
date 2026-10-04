from functools import lru_cache
from typing import Optional
from fastapi import HTTPException, UploadFile, status

from app.biometric.exceptions import InvalidImageError
from app.config.settings import settings
from app.services.biometric_service import BiometricService
from app.storage.base import BiometricRepository
from app.storage.factory import get_biometric_repository
from app.utils.logging import logger

# Maximum permissible image payload size: 10 MB
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_MIMETYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/bmp",
    "application/octet-stream",
}


@lru_cache()
def get_service_singleton() -> BiometricService:
    """Returns singleton instance of BiometricService for application lifecycle."""
    return BiometricService()


def get_biometric_service() -> BiometricService:
    """
    FastAPI dependency injecting the BiometricService.
    Facilitates test mocking via app.dependency_overrides.
    """
    return get_service_singleton()


def get_repository() -> BiometricRepository:
    """FastAPI dependency injecting the configured BiometricRepository."""
    return get_biometric_repository()


async def validate_and_read_image(file: UploadFile) -> bytes:
    """
    Validates uploaded image file:
    - Verifies filename and mime type
    - Enforces file size limitations
    - Returns raw bytes for cv2 decoding
    """
    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An image file is required.",
        )

    # Check content type if available
    content_type = file.content_type.lower() if file.content_type else "application/octet-stream"
    if content_type not in ALLOWED_IMAGE_MIMETYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported image media type '{content_type}'. Supported: JPEG, PNG, WEBP, BMP.",
        )

    try:
        content = await file.read()
    except Exception as e:
        logger.error(f"Failed to read uploaded file: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read uploaded image data.",
        )

    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded image file is empty (0 bytes).",
        )

    if len(content) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image size exceeds maximum limit of {MAX_IMAGE_SIZE_BYTES // (1024 * 1024)}MB.",
        )

    return content
