import uuid
from datetime import datetime, timezone
from typing import Any
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    JSON,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class UserModel(Base):
    """
    SQLAlchemy ORM model for enrolled users.
    Maps unique enterprise / student user identifiers to biometric identities.
    """
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    email = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    password_hash = Column(String(255), nullable=True)
    role = Column(String(32), nullable=False, default="student", index=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    templates = relationship(
        "BiometricTemplateModel",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    attendance_records = relationship(
        "AttendanceModel",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<UserModel(id='{self.id}', user_id='{self.user_id}', name='{self.name}', role='{self.role}')>"


class BiometricTemplateModel(Base):
    """
    SQLAlchemy ORM model for 512-dimensional facial biometric templates.
    Leverages pgvector's Vector(512) for vector storage and hardware-accelerated nearest-neighbor queries.
    Raw facial images are strictly omitted to maintain privacy and compliance.
    """
    __tablename__ = "biometric_templates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(64),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    embedding = Column(Vector(512), nullable=False)
    model_name = Column(String(64), nullable=False, default="buffalo_l")
    model_version = Column(String(32), nullable=False, default="1.0.0")
    status = Column(String(32), nullable=False, default="active", index=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    user = relationship("UserModel", back_populates="templates")

    __table_args__ = (
        Index(
            "idx_biometric_templates_embedding_l2",
            embedding,
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_l2_ops"},
        ),
    )

    def __repr__(self) -> str:
        return f"<BiometricTemplateModel(id='{self.id}', user_id='{self.user_id}', model='{self.model_name}')>"


class AuthenticationLogModel(Base):
    """
    SQLAlchemy ORM model for auditing biometric authentication attempts.
    Contains decision metadata and scoring without raw embeddings or facial captures.
    """
    __tablename__ = "authentication_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(64), nullable=True, index=True)  # Nullable for unverified unknown faces
    timestamp = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    verification_type = Column(String(32), nullable=False)  # '1:1_VERIFICATION' or '1:N_IDENTIFICATION'
    similarity = Column(Float, nullable=True)
    distance = Column(Float, nullable=True)
    threshold = Column(Float, nullable=False)
    result = Column(String(32), nullable=False)  # 'SUCCESS' or 'FAILURE'
    error_code = Column(String(64), nullable=True)
    device_id = Column(String(64), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<AuthenticationLogModel(id='{self.id}', user_id='{self.user_id}', "
            f"type='{self.verification_type}', result='{self.result}')>"
        )


class AttendanceModel(Base):
    """
    SQLAlchemy ORM model for recording student biometric attendance events.
    Enforces uniqueness per (user_id, attendance_date) to prevent duplicate
    attendance records on the same calendar day.
    """
    __tablename__ = "attendance"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(64),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    attendance_date = Column(Date, nullable=False, index=True)
    marked_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    status = Column(String(32), nullable=False, default="Present")
    recognition_similarity = Column(Float, nullable=True)
    recognition_distance = Column(Float, nullable=True)
    device_id = Column(String(64), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    user = relationship("UserModel", back_populates="attendance_records")

    __table_args__ = (
        UniqueConstraint("user_id", "attendance_date", name="uq_user_attendance_date"),
    )

    def __repr__(self) -> str:
        return (
            f"<AttendanceModel(id='{self.id}', user_id='{self.user_id}', "
            f"date='{self.attendance_date}', status='{self.status}')>"
        )

