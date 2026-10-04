from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.dependencies import get_biometric_service, validate_and_read_image
from app.api.schemas.biometric import (
    EnrollmentResponse,
    ErrorResponse,
    IdentificationResponse,
    VerificationResponse,
)
from app.services.biometric_service import BiometricService
from app.utils.logging import logger

router = APIRouter(prefix="/auth", tags=["Biometric Authentication"])


@router.post(
    "/enroll",
    response_model=EnrollmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enroll Biometric Identity",
    description=(
        "Enrolls a new 512-dimensional facial biometric template for a unique user. "
        "Enforces single-face detection and saves the template to PostgreSQL (or local fallback). "
        "Raw face images are NOT stored in the database."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Invalid image, missing face, or multiple faces"},
        500: {"model": ErrorResponse, "description": "Internal database or processing error"},
    },
)
async def enroll_user(
    user_id: str = Form(..., description="Unique user identifier (e.g. USR_001, roll number)"),
    name: str = Form(..., description="Full display name of the user"),
    image: UploadFile = File(..., description="Face photograph for biometric enrollment"),
    service: BiometricService = Depends(get_biometric_service),
) -> EnrollmentResponse:
    clean_user_id = user_id.strip()
    clean_name = name.strip()

    if not clean_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id must be a non-empty string.",
        )
    if not clean_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="name must be a non-empty string.",
        )

    image_bytes = await validate_and_read_image(image)

    result = service.enroll(
        user_id=clean_user_id,
        image_input=image_bytes,
        metadata={"name": clean_name, "source": "api_enrollment"},
    )

    if not result.success:
        if result.error_code in (
            "NO_FACE_DETECTED",
            "MULTIPLE_FACES_DETECTED",
            "INVALID_IMAGE",
            "INVALID_USER_ID",
            "INVALID_EMBEDDING",
            "LIVENESS_CHECK_FAILED",
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.message,
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.message or "Internal biometric enrollment failure.",
        )

    return EnrollmentResponse(
        success=True,
        user_id=result.user_id,
        message="Biometric enrollment successful",
        template_id=result.metadata.get("template_id"),
    )


@router.post(
    "/verify",
    response_model=VerificationResponse,
    summary="1:1 Biometric Verification",
    description=(
        "Performs 1:1 facial verification against enrolled templates of a claimed user ID. "
        "Records an immutable audit entry in authentication_logs."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Invalid image or no face detected"},
        404: {"model": ErrorResponse, "description": "Claimed user not found or not enrolled"},
        500: {"model": ErrorResponse, "description": "Internal database or processing error"},
    },
)
async def verify_user(
    user_id: str = Form(..., description="Claimed user identifier to verify against"),
    image: UploadFile = File(..., description="Live probe face photograph"),
    threshold: Optional[float] = Form(None, description="Optional custom Euclidean distance threshold"),
    device_id: Optional[str] = Form(None, description="Optional client device identifier for audit trail"),
    service: BiometricService = Depends(get_biometric_service),
) -> VerificationResponse:
    clean_user_id = user_id.strip()
    if not clean_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id must be a non-empty string.",
        )

    image_bytes = await validate_and_read_image(image)

    result = service.verify(
        user_id=clean_user_id,
        image_input=image_bytes,
        threshold=threshold,
        device_id=device_id,
    )

    if result.error_code == "USER_NOT_ENROLLED":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result.message,
        )
    if result.error_code in ("NO_FACE_DETECTED", "INVALID_IMAGE", "LIVENESS_CHECK_FAILED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.message,
        )
    if not result.success and result.error_code == "INTERNAL_ERROR":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.message or "Internal verification failure.",
        )

    message = "Identity verified" if result.matched else result.message
    return VerificationResponse(
        authenticated=result.matched,
        user_id=clean_user_id,
        similarity=result.similarity,
        distance=result.distance,
        message=message,
    )


@router.post(
    "/identify",
    response_model=IdentificationResponse,
    summary="1:N Biometric Identification",
    description=(
        "Performs 1:N facial search across the enrolled biometric gallery using pgvector similarity search. "
        "Records an immutable audit entry in authentication_logs."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Invalid image or no face detected"},
        500: {"model": ErrorResponse, "description": "Internal database or processing error"},
    },
)
async def identify_user(
    image: UploadFile = File(..., description="Live probe face photograph"),
    threshold: Optional[float] = Form(None, description="Optional custom Euclidean distance threshold"),
    device_id: Optional[str] = Form(None, description="Optional client device identifier for audit trail"),
    service: BiometricService = Depends(get_biometric_service),
) -> IdentificationResponse:
    image_bytes = await validate_and_read_image(image)

    result = service.identify(
        image_input=image_bytes,
        threshold=threshold,
        device_id=device_id,
    )

    if result.error_code in ("NO_FACE_DETECTED", "INVALID_IMAGE", "LIVENESS_CHECK_FAILED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.message,
        )
    if not result.success and result.error_code == "INTERNAL_ERROR":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.message or "Internal identification failure.",
        )

    if result.matched:
        return IdentificationResponse(
            authenticated=True,
            user_id=result.user_id,
            similarity=result.similarity,
            distance=result.distance,
            message="Identity identified",
        )
    else:
        return IdentificationResponse(
            authenticated=False,
            user_id=None,
            similarity=result.similarity,
            distance=result.distance,
            message="No matching identity found",
        )
