from typing import Optional
from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_biometric_service,
    rate_limit_attendance,
    validate_and_read_image,
)
from app.api.schemas.student import AttendanceMarkResponse
from app.database.connection import get_db
from app.services.attendance_service import AttendanceService
from app.services.biometric_service import BiometricService

router = APIRouter(prefix="/attendance", tags=["Attendance"])


@router.post(
    "/mark",
    response_model=AttendanceMarkResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark attendance via kiosk biometric facial recognition",
)
async def mark_attendance(
    image: UploadFile = File(..., description="Live probe face photograph"),
    device_id: Optional[str] = Form(None, description="Optional kiosk / gate identifier"),
    db: Session = Depends(get_db),
    biometric_service: BiometricService = Depends(get_biometric_service),
    _rate_limit: None = Depends(rate_limit_attendance),
) -> AttendanceMarkResponse:
    """
    Kiosk attendance processing pipeline:
    1. Validates image MIME and file size limitations.
    2. Runs presentation attack detection (liveness).
    3. Executes 1:N pgvector-backed similarity identification.
    4. Enforces same-day duplicate attendance prevention per student.
    5. Records attendance with decision metadata in PostgreSQL.
    """
    image_bytes = await validate_and_read_image(image)

    result = AttendanceService.mark_attendance(
        image_bytes=image_bytes,
        device_id=device_id,
        db=db,
        biometric_service=biometric_service,
    )

    return AttendanceMarkResponse(**result)
