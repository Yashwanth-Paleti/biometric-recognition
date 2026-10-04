from typing import Any, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_biometric_service,
    rate_limit_student_auth,
    validate_and_read_image,
)
from app.api.schemas.student import (
    StudentAttendanceStatsResponse,
    StudentLoginRequest,
    StudentLoginResponse,
    StudentProfileResponse,
    StudentRegisterResponse,
)
from app.database.connection import get_db
from app.services.attendance_service import AttendanceService
from app.services.biometric_service import BiometricService
from app.services.student_service import StudentService
from app.utils.logging import logger
from app.utils.security import get_current_student

router = APIRouter(prefix="/students", tags=["Students"])


@router.post(
    "/register",
    response_model=StudentRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new student with dual biometric templates",
)
async def register_student(
    name: str = Form(..., description="Student full name"),
    student_id: str = Form(..., description="Unique student ID / roll number"),
    email: Optional[str] = Form(None, description="Student email address"),
    password: str = Form(..., min_length=6, description="Account password"),
    confirm_password: str = Form(..., min_length=6, description="Confirm password"),
    image1: UploadFile = File(..., description="Face capture 1"),
    image2: UploadFile = File(..., description="Face capture 2"),
    db: Session = Depends(get_db),
    biometric_service: BiometricService = Depends(get_biometric_service),
    _rate_limit: None = Depends(rate_limit_student_auth),
) -> StudentRegisterResponse:
    """
    Enrolls a student into the biometric attendance portal:
    - Validates fields, password confirmation, unique student ID, and unique email
    - Verifies liveness and extracts 512-D normalized embeddings for both photos
    - Persists two biometric templates linked to the student
    - Rolls back the entire registration if either photo fails liveness/extraction
    """
    img1_bytes = await validate_and_read_image(image1)
    img2_bytes = await validate_and_read_image(image2)

    user = StudentService.register_student(
        name=name,
        student_id=student_id,
        email=email,
        password=password,
        confirm_password=confirm_password,
        image1_bytes=img1_bytes,
        image2_bytes=img2_bytes,
        db=db,
        biometric_service=biometric_service,
    )

    return StudentRegisterResponse(
        success=True,
        student_id=user.user_id,
        name=user.name,
        email=user.email,
        message="Student registration and dual biometric enrollment completed successfully.",
    )


@router.post(
    "/login",
    response_model=StudentLoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate student and issue JWT Bearer token",
)
async def login_student(
    req: StudentLoginRequest,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_student_auth),
) -> StudentLoginResponse:
    """
    Validates student credentials (Student ID or email + password via bcrypt)
    and returns a signed JWT with role='student'.
    """
    result = StudentService.login_student(
        identifier=req.identifier,
        password=req.password,
        db=db,
    )
    return StudentLoginResponse(**result)


@router.get(
    "/me",
    response_model=StudentProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Get authenticated student profile",
)
async def get_student_me(
    current_student: dict[str, Any] = Depends(get_current_student),
    db: Session = Depends(get_db),
) -> StudentProfileResponse:
    """
    Returns profile details for the currently authenticated student.
    Enforces student-only role authorization.
    """
    user = StudentService.get_student_profile(current_student["user_id"], db)
    return StudentProfileResponse(
        student_id=user.user_id,
        name=user.name,
        email=user.email,
        role=user.role,
        status=user.status,
        created_at=user.created_at.isoformat() if user.created_at else None,
    )


@router.get(
    "/attendance",
    response_model=StudentAttendanceStatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get attendance statistics and history for student dashboard",
)
async def get_student_attendance(
    current_student: dict[str, Any] = Depends(get_current_student),
    db: Session = Depends(get_db),
) -> StudentAttendanceStatsResponse:
    """
    Computes attendance percentage and retrieves chronological attendance history
    strictly for the authenticated student.
    """
    return AttendanceService.get_student_attendance_stats(current_student["user_id"], db)
