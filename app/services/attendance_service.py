from datetime import datetime, timezone
from typing import Any, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.api.schemas.student import AttendanceRecordItem, StudentAttendanceStatsResponse
from app.database.models import AttendanceModel, UserModel
from app.models.biometric import AuthenticationResult
from app.services.biometric_service import BiometricService
from app.utils.logging import logger


class AttendanceService:
    """
    Domain service for biometric attendance marking and history calculation.
    Integrates with pgvector-backed 1:N identification and enforces same-day duplicate prevention.
    """

    @staticmethod
    def mark_attendance(
        image_bytes: bytes,
        device_id: Optional[str],
        db: Session,
        biometric_service: BiometricService,
    ) -> dict[str, Any]:
        """
        Processes a live probe photograph:
        1. Executes liveness detection and 1:N biometric identification.
        2. If unrecognized, safely returns non-authenticated response.
        3. If recognized, checks for existing attendance record on the current UTC date.
        4. If already recorded today, prevents duplicate insertion and returns notice.
        5. If new, inserts an AttendanceModel record and returns confirmation.
        """
        if not image_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A face image capture is required to mark attendance.",
            )

        effective_device = device_id or "KIOSK_MAIN"
        logger.info(f"Attendance marking initiated from device: {effective_device}")

        # Run 1:N Identification via BiometricService
        auth_result: AuthenticationResult = biometric_service.identify(
            image_input=image_bytes,
            device_id=effective_device,
        )

        if not auth_result.matched or not auth_result.user_id:
            logger.info("Attendance mark rejected: No matching face identity found.")
            return {
                "success": False,
                "authenticated": False,
                "user_id": None,
                "name": None,
                "status": None,
                "message": auth_result.message or "No matching identity found for face capture.",
                "already_marked": False,
                "marked_at": None,
                "similarity": auth_result.similarity,
                "distance": auth_result.distance,
            }

        student_id = auth_result.user_id
        student = db.query(UserModel).filter(UserModel.user_id == student_id).first()
        student_name = student.name if student else student_id

        # Determine current date (UTC)
        now_utc = datetime.now(timezone.utc)
        today_date = now_utc.date()

        # Check for same-day duplicate attendance
        existing_record = db.query(AttendanceModel).filter(
            AttendanceModel.user_id == student_id,
            AttendanceModel.attendance_date == today_date,
        ).first()

        if existing_record is not None:
            logger.info(
                f"Duplicate attendance attempted for student '{student_id}' on date {today_date}."
            )
            return {
                "success": False,
                "authenticated": True,
                "user_id": student_id,
                "name": student_name,
                "status": existing_record.status,
                "message": "Attendance already marked today.",
                "already_marked": True,
                "marked_at": existing_record.marked_at.isoformat() if existing_record.marked_at else None,
                "similarity": auth_result.similarity,
                "distance": auth_result.distance,
            }

        # Create new attendance record
        new_record = AttendanceModel(
            user_id=student_id,
            attendance_date=today_date,
            marked_at=now_utc,
            status="Present",
            recognition_similarity=auth_result.similarity,
            recognition_distance=auth_result.distance,
            device_id=effective_device,
        )

        try:
            db.add(new_record)
            db.commit()
            db.refresh(new_record)
            logger.info(
                f"Attendance marked successfully for student '{student_id}' at {new_record.marked_at}."
            )
            return {
                "success": True,
                "authenticated": True,
                "user_id": student_id,
                "name": student_name,
                "status": "Present",
                "message": f"Attendance marked successfully for {student_name}.",
                "already_marked": False,
                "marked_at": new_record.marked_at.isoformat(),
                "similarity": auth_result.similarity,
                "distance": auth_result.distance,
            }
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to record attendance in database for '{student_id}': {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to record attendance in the database.",
            )

    @staticmethod
    def get_student_attendance_stats(
        student_id: str,
        db: Session,
    ) -> StudentAttendanceStatsResponse:
        """
        Calculates student attendance metrics:
        - attendance percentage (rounded to 1 decimal place)
        - present count
        - total sessions
        - last attendance timestamp
        - formatted history list
        """
        student = db.query(UserModel).filter(UserModel.user_id == student_id).first()
        if student is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Student '{student_id}' not found.",
            )

        records = (
            db.query(AttendanceModel)
            .filter(AttendanceModel.user_id == student_id)
            .order_by(AttendanceModel.marked_at.desc())
            .all()
        )

        present_count = len([r for r in records if r.status.lower() == "present"])
        # For the attendance demo: if 0 records, total is 0. If records exist, total sessions is max(present_count, 1)
        total_sessions = present_count if present_count > 0 else 0

        if total_sessions == 0:
            percentage = 0.0
        else:
            percentage = round((present_count / total_sessions) * 100.0, 1)

        last_attendance_str = None
        if records:
            last_record = records[0]
            if last_record.marked_at:
                last_attendance_str = last_record.marked_at.strftime("%d %b %Y, %I:%M %p")
            else:
                last_attendance_str = str(last_record.attendance_date)

        history_items = [
            AttendanceRecordItem(
                id=r.id,
                date=r.marked_at.strftime("%d %b %Y") if r.marked_at else str(r.attendance_date),
                time=r.marked_at.strftime("%I:%M %p") if r.marked_at else "",
                status=r.status,
                similarity=round(r.recognition_similarity, 4) if r.recognition_similarity is not None else None,
                distance=round(r.recognition_distance, 4) if r.recognition_distance is not None else None,
                device_id=r.device_id,
            )
            for r in records
        ]

        return StudentAttendanceStatsResponse(
            student_id=student.user_id,
            name=student.name,
            email=student.email,
            attendance_percentage=percentage,
            present_count=present_count,
            total_sessions=total_sessions,
            last_attendance=last_attendance_str,
            history=history_items,
        )
