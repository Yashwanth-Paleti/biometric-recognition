import os
import uuid
import numpy as np
import pytest
from sqlalchemy import create_engine, select

from app.biometric.exceptions import EmbeddingExtractionError
from app.config.settings import settings
from app.database.connection import check_database_health, get_session_factory
from app.database.models import (
    AuthenticationLogModel,
    Base,
    BiometricTemplateModel,
    UserModel,
)
from app.models.biometric import BiometricTemplate, User
from app.storage.factory import get_biometric_repository
from app.storage.local_repository import LocalBiometricRepository
from app.storage.postgres_repository import PostgresBiometricRepository


# ============================================================================
# ORM Model Schema & Integrity Tests
# ============================================================================
def test_user_model_fields():
    user = UserModel(
        id=str(uuid.uuid4()),
        user_id="USR_TEST_01",
        name="Test User",
        email="test@example.com",
        status="active",
    )
    assert user.user_id == "USR_TEST_01"
    assert user.name == "Test User"
    assert user.email == "test@example.com"
    assert user.status == "active"
    assert "UserModel" in repr(user)


def test_biometric_template_model_fields():
    vec = [0.1] * 512
    template = BiometricTemplateModel(
        id=str(uuid.uuid4()),
        user_id="USR_TEST_01",
        embedding=vec,
        model_name="buffalo_l",
        model_version="1.0.0",
        status="active",
        metadata_json={"camera": "entry_gate"},
    )
    assert template.user_id == "USR_TEST_01"
    assert len(template.embedding) == 512
    assert template.metadata_json == {"camera": "entry_gate"}
    assert "BiometricTemplateModel" in repr(template)


def test_authentication_log_model_fields_and_privacy():
    log = AuthenticationLogModel(
        id=str(uuid.uuid4()),
        user_id="USR_TEST_01",
        verification_type="1:1_VERIFICATION",
        similarity=0.912,
        distance=0.420,
        threshold=0.85,
        result="SUCCESS",
        error_code=None,
        device_id="gate_terminal_01",
    )
    assert log.user_id == "USR_TEST_01"
    assert log.verification_type == "1:1_VERIFICATION"
    assert log.result == "SUCCESS"
    assert log.similarity == 0.912

    # PRIVACY CRITICAL REQUIREMENT: Verify model schema does NOT store raw images or embeddings
    column_names = [c.name for c in AuthenticationLogModel.__table__.columns]
    assert "embedding" not in column_names
    assert "image" not in column_names
    assert "raw_image" not in column_names
    assert "password" not in column_names
    assert "token" not in column_names


# ============================================================================
# Vector Validation in PostgresBiometricRepository
# ============================================================================
def test_postgres_repo_vector_sanitization_valid():
    repo = PostgresBiometricRepository()
    # Random unit vector of dimension 512
    vec = np.random.randn(512).astype(np.float32)
    vec = vec / np.linalg.norm(vec)

    sanitized = repo._validate_and_sanitize_vector(vec)
    assert isinstance(sanitized, list)
    assert len(sanitized) == 512
    assert all(isinstance(x, float) for x in sanitized)


def test_postgres_repo_vector_sanitization_wrong_dimension():
    repo = PostgresBiometricRepository()
    vec_128 = np.random.randn(128).astype(np.float32)

    with pytest.raises(EmbeddingExtractionError) as exc_info:
        repo._validate_and_sanitize_vector(vec_128)
    assert "Invalid embedding dimension" in str(exc_info.value)


def test_postgres_repo_vector_sanitization_non_finite():
    repo = PostgresBiometricRepository()
    vec_nan = np.ones(512, dtype=np.float32)
    vec_nan[10] = np.nan

    with pytest.raises(EmbeddingExtractionError) as exc_info:
        repo._validate_and_sanitize_vector(vec_nan)
    assert "non-finite" in str(exc_info.value)


# ============================================================================
# Storage Backend Factory Selection
# ============================================================================
def test_repository_factory_selection():
    repo_local = get_biometric_repository("local")
    assert isinstance(repo_local, LocalBiometricRepository)

    repo_postgres = get_biometric_repository("postgres")
    assert isinstance(repo_postgres, PostgresBiometricRepository)


# ============================================================================
# Live PostgreSQL + pgvector Integration Test (Skipped if DB not connected)
# ============================================================================
def is_live_postgres_available() -> bool:
    """Checks if live PostgreSQL instance is available with pgvector."""
    if not settings.database_url:
        return False
    try:
        return check_database_health()
    except Exception:
        return False


@pytest.mark.skipif(
    not is_live_postgres_available(),
    reason="PostgreSQL not running or DATABASE_URL not configured. Skipping live database test.",
)
def test_live_postgres_crud_and_vector_search():
    """
    Live end-to-end database test:
    - User creation
    - Template creation with vector(512)
    - 1:N similarity search using pgvector
    - Audit logging
    - Template deletion
    """
    repo = PostgresBiometricRepository()

    test_uid = f"PG_USER_{uuid.uuid4().hex[:6]}"
    vec = np.random.randn(512).astype(np.float32)
    vec = vec / np.linalg.norm(vec)

    tmpl = BiometricTemplate(
        user_id=test_uid,
        embedding=vec,
        model_name="buffalo_l",
        model_version="1.0.0",
        metadata={"name": "Postgres Test User"},
    )

    try:
        # 1. Save template
        saved = repo.save_template(tmpl)
        assert saved is True

        # 2. Retrieve template by user
        templates = repo.get_templates(test_uid)
        assert len(templates) >= 1
        assert templates[0].user_id == test_uid

        # 3. Native pgvector 1:N similarity search
        best_match, sim, dist = repo.find_nearest_template(vec, threshold=0.85)
        assert best_match is not None
        assert best_match.user_id == test_uid
        assert dist < 0.05  # Same vector distance ~ 0

        # 4. Record audit log
        log_res = repo.log_authentication(
            user_id=test_uid,
            verification_type="1:N_IDENTIFICATION",
            result="SUCCESS",
            threshold=0.85,
            similarity=sim,
            distance=dist,
        )
        assert log_res is True

        # 5. Delete template
        deleted = repo.delete_template(tmpl.template_id)
        assert deleted is True

    finally:
        repo.delete_templates_by_user(test_uid)
