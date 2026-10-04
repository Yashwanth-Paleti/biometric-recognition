"""initial biometric schema with pgvector

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-10-02 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=32), server_default='active', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_users_user_id', 'users', ['user_id'], unique=True)
    op.create_index('ix_users_status', 'users', ['status'], unique=False)

    # 3. Create biometric_templates table with vector(512)
    op.create_table(
        'biometric_templates',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=False),
        sa.Column('embedding', Vector(512), nullable=False),
        sa.Column('model_name', sa.String(length=64), server_default='buffalo_l', nullable=False),
        sa.Column('model_version', sa.String(length=32), server_default='1.0.0', nullable=False),
        sa.Column('status', sa.String(length=32), server_default='active', nullable=False),
        sa.Column('metadata_json', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_biometric_templates_user_id', 'biometric_templates', ['user_id'], unique=False)
    op.create_index('ix_biometric_templates_status', 'biometric_templates', ['status'], unique=False)

    # HNSW vector index for accelerated Euclidean (L2) distance nearest neighbor search
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_biometric_templates_embedding_l2 "
        "ON biometric_templates USING hnsw (embedding vector_l2_ops) "
        "WITH (m = 16, ef_construction = 64);"
    )

    # 4. Create authentication_logs table
    op.create_table(
        'authentication_logs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('verification_type', sa.String(length=32), nullable=False),
        sa.Column('similarity', sa.Float(), nullable=True),
        sa.Column('distance', sa.Float(), nullable=True),
        sa.Column('threshold', sa.Float(), nullable=False),
        sa.Column('result', sa.String(length=32), nullable=False),
        sa.Column('error_code', sa.String(length=64), nullable=True),
        sa.Column('device_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_authentication_logs_user_id', 'authentication_logs', ['user_id'], unique=False)
    op.create_index('ix_authentication_logs_timestamp', 'authentication_logs', ['timestamp'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_authentication_logs_timestamp', table_name='authentication_logs')
    op.drop_index('ix_authentication_logs_user_id', table_name='authentication_logs')
    op.drop_table('authentication_logs')

    op.execute("DROP INDEX IF EXISTS idx_biometric_templates_embedding_l2")
    op.drop_index('ix_biometric_templates_status', table_name='biometric_templates')
    op.drop_index('ix_biometric_templates_user_id', table_name='biometric_templates')
    op.drop_table('biometric_templates')

    op.drop_index('ix_users_status', table_name='users')
    op.drop_index('ix_users_user_id', table_name='users')
    op.drop_table('users')

    op.execute("DROP EXTENSION IF EXISTS vector")
