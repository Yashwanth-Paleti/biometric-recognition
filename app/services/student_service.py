from datetime import datetime, timezone
from typing import Any, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.database.models import BiometricTemplateModel, UserModel
from app.models.biometric import AuthenticationResult
from app.services.biometric_service import BiometricService
from app.utils.logging import logger
from app.utils.security import create_access_token, hash_password, verify_password


class StudentService:
    """
    Domain service for student registration, authentication, and profile retrieval.
    Reuses existing bcrypt password utilities, JWT creation, and BiometricService.
    """

    @staticmethod
    def register_student(
        name: str,
        student_id: str,
        email: Optional[str],
        password: str,
        confirm_password: str,
        image1_bytes: bytes,
        image2_bytes: bytes,
        db: Session,
        biometric_service: BiometricService,
    ) -> UserModel:
        """
        Registers a new student account with dual biometric template enrollment.
        Enforces atomic rollback if biometric enrollment or liveness validation fails on either image.
        """
        # 1. Field validations
        name = (name or "").strip()
        student_id = (student_id or "").strip()
        email = (email or "").strip().lower() if email else None
        password = password or ""
        confirm_password = confirm_password or ""

        if not name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Full Name is required.",
            )
        if not student_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Student ID is required.",
            )
        if len(password) < 6:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 6 characters.",
            )
        if password != confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password and confirmation password do not match.",
            )

        # 2. Uniqueness checks
        existing_user = db.query(UserModel).filter(UserModel.user_id == student_id).first()
        if existing_user is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Student ID '{student_id}' is already registered.",
            )

        if email:
            existing_email = db.query(UserModel).filter(UserModel.email == email).first()
            if existing_email is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Email '{email}' is already registered.",
                )

        if not image1_bytes or not image2_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Two clear facial photographs are required for biometric registration.",
            )

        # 3. Biometric enrollment for Image 1
        res1: AuthenticationResult = biometric_service.enroll(
            user_id=student_id,
            image_input=image1_bytes,
            metadata={"name": name, "capture_index": 1},
        )
        if not res1.success:
            logger.warning(f"Registration failed on Image 1 for {student_id}: {res1.message}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Face Image 1 enrollment failed: {res1.message}",
            )

        # 4. Biometric enrollment for Image 2 (Rollback on failure)
        res2: AuthenticationResult = biometric_service.enroll(
            user_id=student_id,
            image_input=image2_bytes,
            metadata={"name": name, "capture_index": 2},
        )
        if not res2.success:
            logger.warning(
                f"Registration failed on Image 2 for {student_id}: {res2.message}. Rolling back..."
            )
            # Rollback: Clean up any templates and user created for this student_id
            try:
                db.query(BiometricTemplateModel).filter(
                    BiometricTemplateModel.user_id == student_id
                ).delete()
                db.query(UserModel).filter(UserModel.user_id == student_id).delete()
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Error rolling back failed registration for {student_id}: {e}")

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Face Image 2 enrollment failed: {res2.message}. Registration rolled back.",
            )

        # 5. Finalize user record with password_hash, role, and details
        user = db.query(UserModel).filter(UserModel.user_id == student_id).first()
        if user is None:
            user = UserModel(
                user_id=student_id,
                name=name,
                email=email,
                status="active",
            )
            db.add(user)

        user.name = name
        user.email = email
        user.password_hash = hash_password(password)
        user.role = "student"
        user.status = "active"

        try:
            db.commit()
            db.refresh(user)
            logger.info(f"Student '{student_id}' successfully registered with 2 biometric templates.")
            return user
        except Exception as e:
            db.rollback()
            # Clean up on commit failure
            db.query(BiometricTemplateModel).filter(
                BiometricTemplateModel.user_id == student_id
            ).delete()
            db.query(UserModel).filter(UserModel.user_id == student_id).delete()
            db.commit()
            logger.error(f"Failed to finalize student registration for {student_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to finalize student registration. Please try again.",
            )

    @staticmethod
    def login_student(
        identifier: str,
        password: str,
        db: Session,
    ) -> dict[str, Any]:
        """
        Authenticates a student using Student ID or email, verifies password via bcrypt,
        and returns a signed student JWT token.
        """
        identifier = (identifier or "").strip()
        if not identifier or not password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Student ID/email and password are required.",
            )

        # Query user by user_id or email
        user = db.query(UserModel).filter(
            (UserModel.user_id == identifier) | (UserModel.email == identifier.lower())
        ).first()

        if user is None or not user.password_hash:
            logger.warning(f"Student login failed: Unknown or uninitialized user '{identifier}'.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Student ID/email or password.",
            )

        if user.role != "student":
            logger.warning(f"Student login rejected for '{identifier}': User role is '{user.role}'.")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Account is not a student account.",
            )

        if not verify_password(password, user.password_hash):
            logger.warning(f"Student login failed: Invalid password for '{identifier}'.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Student ID/email or password.",
            )

        access_token = create_access_token({
            "sub": user.user_id,
            "role": "student",
            "name": user.name,
        })

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "student_id": user.user_id,
            "name": user.name,
            "role": user.role,
        }

    @staticmethod
    def get_student_profile(student_id: str, db: Session) -> UserModel:
        """Retrieves active student profile by student_id."""
        user = db.query(UserModel).filter(
            UserModel.user_id == student_id,
            UserModel.role == "student"
        ).first()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Student record for ID '{student_id}' not found.",
            )
        return user
