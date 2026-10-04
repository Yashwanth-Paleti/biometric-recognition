from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field


class StudentRegisterResponse(BaseModel):
    """Response payload for successful student registration."""
    success: bool = Field(default=True, description="Indicates whether student was enrolled successfully")
    student_id: str = Field(description="Unique student identifier")
    name: str = Field(description="Student full name")
    email: Optional[str] = Field(default=None, description="Student email address")
    message: str = Field(
        default="Student registration and biometric enrollment successful.",
        description="Human-readable result summary"
    )


class StudentLoginRequest(BaseModel):
    """Payload for student login."""
    identifier: str = Field(..., description="Student ID or registered email address")
    password: str = Field(..., min_length=1, description="Student password")


class StudentLoginResponse(BaseModel):
    """Response payload containing JWT token on successful login."""
    access_token: str = Field(description="Signed JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    student_id: str = Field(description="Student identifier")
    name: str = Field(description="Student display name")
    role: str = Field(default="student", description="Assigned role claim")


class StudentProfileResponse(BaseModel):
    """Student profile information."""
    student_id: str = Field(description="Student ID")
    name: str = Field(description="Student name")
    email: Optional[str] = Field(default=None, description="Registered email")
    role: str = Field(description="Role")
    status: str = Field(description="Account status")
    created_at: Optional[str] = Field(default=None, description="Account creation timestamp")


class AttendanceRecordItem(BaseModel):
    """Single attendance history log entry."""
    id: str = Field(description="Attendance record ID")
    date: str = Field(description="Formatted date (e.g. '04 Oct 2026')")
    time: str = Field(description="Formatted time (e.g. '10:42 PM')")
    status: str = Field(default="Present", description="Attendance status")
    similarity: Optional[float] = Field(default=None, description="Recognition similarity score")
    distance: Optional[float] = Field(default=None, description="Recognition Euclidean distance")
    device_id: Optional[str] = Field(default=None, description="Kiosk or camera identifier")


class StudentAttendanceStatsResponse(BaseModel):
    """Full attendance statistics and history payload for student dashboard."""
    student_id: str = Field(description="Student ID")
    name: str = Field(description="Student name")
    email: Optional[str] = Field(default=None, description="Student email")
    attendance_percentage: float = Field(description="Calculated attendance percentage (0.0 to 100.0)")
    present_count: int = Field(description="Total sessions attended/present")
    total_sessions: int = Field(description="Total conducted sessions")
    last_attendance: Optional[str] = Field(default=None, description="Timestamp or formatted string of last attendance")
    history: list[AttendanceRecordItem] = Field(default_factory=list, description="Chronological attendance history")


class AttendanceMarkResponse(BaseModel):
    """Result payload for kiosk attendance marking."""
    success: bool = Field(description="True if attendance was marked or recognized")
    authenticated: bool = Field(description="True if face was identified against enrolled database")
    user_id: Optional[str] = Field(default=None, description="Identified student ID")
    name: Optional[str] = Field(default=None, description="Identified student name")
    department: Optional[str] = Field(default=None, description="Student department or academic program")
    status: Optional[str] = Field(default=None, description="Attendance status (e.g. 'Present')")
    message: str = Field(description="Detailed result message")
    marked_at: Optional[str] = Field(default=None, description="ISO-8601 timestamp of attendance")
    already_marked: bool = Field(default=False, description="True if attendance was already recorded today")
    similarity: Optional[float] = Field(default=None, description="Biometric similarity score")
    distance: Optional[float] = Field(default=None, description="Biometric distance score")

