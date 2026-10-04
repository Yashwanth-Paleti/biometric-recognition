"""Add student authentication fields and attendance table

Revision ID: 002_student_auth_attendance
Revises: 001_initial_schema
Create Date: 2026-10-04 20:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '002_student_auth_attendance'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add password_hash and role columns to users table
    op.add_column('users', sa.Column('password_hash', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('role', sa.String(length=32), server_default='student', nullable=False))
    op.create_index('ix_users_role', 'users', ['role'], unique=False)
    op.create_index('ix_users_email', 'users', ['email'], unique=False)

    # 2. Create attendance table
    op.create_table(
        'attendance',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=False),
        sa.Column('attendance_date', sa.Date(), nullable=False),
        sa.Column('marked_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='Present', nullable=False),
        sa.Column('recognition_similarity', sa.Float(), nullable=True),
        sa.Column('recognition_distance', sa.Float(), nullable=True),
        sa.Column('device_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'attendance_date', name='uq_user_attendance_date'),
    )
    op.create_index('ix_attendance_user_id', 'attendance', ['user_id'], unique=False)
    op.create_index('ix_attendance_attendance_date', 'attendance', ['attendance_date'], unique=False)
    op.create_index('ix_attendance_marked_at', 'attendance', ['marked_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_attendance_marked_at', table_name='attendance')
    op.drop_index('ix_attendance_attendance_date', table_name='attendance')
    op.drop_index('ix_attendance_user_id', table_name='attendance')
    op.drop_table('attendance')

    op.drop_index('ix_users_email', table_name='users')
    op.drop_index('ix_users_role', table_name='users')
    op.drop_column('users', 'role')
    op.drop_column('users', 'password_hash')
