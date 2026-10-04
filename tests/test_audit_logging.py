import io
import logging
from pathlib import Path
import pytest

from app.biometric.liveness import PassThroughLivenessDetector
from app.models.biometric import BiometricTemplate
from app.services.biometric_service import BiometricService
from app.storage.local_repository import LocalBiometricRepository
from app.utils.logging import SanitizedFormatter, setup_logger

BASE_DIR = Path(__file__).resolve().parent.parent
IMAGE_MALHAR = BASE_DIR / "dataset" / "1_Malhar.jpg"


def test_audit_log_success_record_structure(tmp_path):
    """Verifies that successful verifications record all required metadata."""
    repo = LocalBiometricRepository(
        storage_path=tmp_path / "audit_repo.json",
        auto_import_legacy=False,
    )
    service = BiometricService(
        repository=repo,
        liveness_detector=PassThroughLivenessDetector(),
    )

    # Enroll user
    service.enroll(user_id="AUDIT_USR_1", image_input=str(IMAGE_MALHAR))

    # Perform 1:1 verification with custom device_id and threshold
    verify_res = service.verify(
        user_id="AUDIT_USR_1",
        image_input=str(IMAGE_MALHAR),
        threshold=0.80,
        device_id="GATE_TERMINAL_01",
    )
    assert verify_res.matched is True

    logs = repo.get_logs()
    assert len(logs) >= 1
    latest_log = logs[-1]

    # Verify required fields
    assert "timestamp" in latest_log
    assert latest_log["user_id"] == "AUDIT_USR_1"
    assert latest_log["verification_type"] == "1:1_VERIFICATION"
    assert latest_log["result"] == "SUCCESS"
    assert latest_log["threshold"] == 0.80
    assert latest_log["device_id"] == "GATE_TERMINAL_01"
    assert latest_log["distance"] is not None
    assert latest_log["similarity"] is not None
    assert latest_log["error_code"] is None

    # CRITICAL: Verify NO biometric embedding, raw image, or token is stored in audit logs
    assert "embedding" not in latest_log
    assert "vector" not in latest_log
    assert "image" not in latest_log
    assert "password" not in latest_log
    assert "token" not in latest_log


def test_audit_log_failure_records_safely(tmp_path):
    """Verifies that failed verification attempts record failure results and error codes."""
    repo = LocalBiometricRepository(
        storage_path=tmp_path / "audit_fail_repo.json",
        auto_import_legacy=False,
    )
    service = BiometricService(
        repository=repo,
        liveness_detector=PassThroughLivenessDetector(),
    )

    # 1. Non-existent user verification failure
    res1 = service.verify(
        user_id="NON_EXISTENT_ID",
        image_input=str(IMAGE_MALHAR),
        device_id="TURNSTILE_04",
    )
    assert res1.matched is False

    logs = repo.get_logs()
    fail_log = logs[-1]
    assert fail_log["user_id"] == "NON_EXISTENT_ID"
    assert fail_log["result"] == "FAILURE"
    assert fail_log["error_code"] == "USER_NOT_ENROLLED"
    assert fail_log["device_id"] == "TURNSTILE_04"


def test_sanitized_logger_redacts_credentials_and_tokens():
    """Verifies that the SanitizedFormatter masks passwords, Bearer tokens, DB credentials, and vectors."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(SanitizedFormatter(fmt="%(message)s"))

    test_logger = logging.getLogger("test_sanitizer")
    test_logger.handlers.clear()
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.INFO)
    test_logger.propagate = False

    # 1. Password redaction
    test_logger.info("Connecting with password='SuperSecretPassword123' for user admin")
    output = stream.getvalue()
    assert "SuperSecretPassword123" not in output
    assert "[REDACTED_PASSWORD]" in output

    # 2. Bearer JWT token redaction
    test_logger.info("Header Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiJ9.secret")
    output = stream.getvalue()
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in output
    assert "[REDACTED_JWT_TOKEN]" in output

    # 3. Database URL credential redaction
    test_logger.info("Connected to postgresql://postgres:MySecretDbPass@db.supabase.co:5432/biometrics")
    output = stream.getvalue()
    assert "MySecretDbPass" not in output
    assert "***" in output
