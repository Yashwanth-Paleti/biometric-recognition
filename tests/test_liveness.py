from pathlib import Path
from unittest.mock import MagicMock
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api.app import app
from app.api.dependencies import get_biometric_service
from app.biometric.liveness import (
    BaseLivenessDetector,
    LivenessResult,
    PassiveTextureFrequencyLivenessDetector,
    PassThroughLivenessDetector,
)
from app.models.biometric import AuthenticationResult
from app.services.biometric_service import BiometricService
from app.storage.local_repository import LocalBiometricRepository

BASE_DIR = Path(__file__).resolve().parent.parent
IMAGE_MALHAR = BASE_DIR / "dataset" / "1_Malhar.jpg"
IMAGE_HARSH = BASE_DIR / "dataset" / "2_Harsh.jpg"


class RejectAllLivenessDetector(BaseLivenessDetector):
    """Test stub that simulates presentation attack detection by rejecting all frames."""
    def evaluate(self, image_rgb: np.ndarray, face=None) -> LivenessResult:
        return LivenessResult(
            passed=False,
            score=0.12,
            method="test_reject_all",
            details={"reason": "simulated_spoof"},
            message="Presentation attack detected (test spoof).",
        )


class AcceptAllLivenessDetector(BaseLivenessDetector):
    """Test stub that passes all frames."""
    def evaluate(self, image_rgb: np.ndarray, face=None) -> LivenessResult:
        return LivenessResult(
            passed=True,
            score=0.95,
            method="test_accept_all",
            details={"reason": "simulated_live"},
            message="Liveness verified.",
        )


def test_passive_liveness_real_photographs():
    """Verifies that legitimate facial captures pass passive liveness evaluation."""
    assert IMAGE_MALHAR.exists(), f"Image {IMAGE_MALHAR} required"
    detector = PassiveTextureFrequencyLivenessDetector(threshold=0.40)

    # Load and decode image
    bgr = cv2.imread(str(IMAGE_MALHAR))
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    result = detector.evaluate(rgb)
    assert result.passed is True
    assert result.score >= 0.40
    assert result.method == "passive_texture_frequency_v1"
    assert "texture_score" in result.details
    assert "fourier_score" in result.details
    assert "color_score" in result.details


def test_passive_liveness_synthetic_spoof_rejection():
    """Verifies that uniform / flat blurred presentation attacks are rejected."""
    detector = PassiveTextureFrequencyLivenessDetector(threshold=0.40)

    # Flat artificial image (simulates low-contrast or blank surface)
    flat_image = np.full((300, 300, 3), 128, dtype=np.uint8)
    result = detector.evaluate(flat_image)

    assert result.passed is False
    assert result.score < 0.40
    assert "Liveness check failed" in result.message


def test_passthrough_liveness_detector():
    """Verifies that PassThroughLivenessDetector always passes with score 1.0."""
    detector = PassThroughLivenessDetector()
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    res = detector.evaluate(dummy_img)

    assert res.passed is True
    assert res.score == 1.0
    assert res.method == "passthrough"


def test_biometric_service_rejects_on_liveness_failure(tmp_path):
    """
    Verifies that BiometricService intercepts and rejects presentation attacks
    BEFORE biometric verification or enrollment when liveness detector fails.
    """
    repo = LocalBiometricRepository(storage_path=tmp_path / "test_repo.json", auto_import_legacy=False)
    rejecting_service = BiometricService(
        repository=repo,
        liveness_detector=RejectAllLivenessDetector(),
    )

    # 1. Enrollment must be rejected
    enroll_res = rejecting_service.enroll(
        user_id="spoof_user",
        image_input=str(IMAGE_MALHAR),
    )
    assert enroll_res.success is False
    assert enroll_res.matched is False
    assert enroll_res.error_code == "LIVENESS_CHECK_FAILED"
    assert enroll_res.metadata.get("liveness_passed") is False

    # 2. Verification must be rejected before matching
    # First enroll legitimately with accepting detector
    accepting_service = BiometricService(
        repository=repo,
        liveness_detector=AcceptAllLivenessDetector(),
    )
    ok_enroll = accepting_service.enroll(user_id="live_user", image_input=str(IMAGE_MALHAR))
    assert ok_enroll.success is True

    # Now verify with rejecting detector
    verify_res = rejecting_service.verify(
        user_id="live_user",
        image_input=str(IMAGE_MALHAR),
    )
    assert verify_res.success is False
    assert verify_res.matched is False
    assert verify_res.error_code == "LIVENESS_CHECK_FAILED"
    assert "Presentation attack detected" in verify_res.message

    # 3. Identification must be rejected
    ident_res = rejecting_service.identify(image_input=str(IMAGE_MALHAR))
    assert ident_res.success is False
    assert ident_res.matched is False
    assert ident_res.error_code == "LIVENESS_CHECK_FAILED"


def test_api_liveness_rejection_http_400():
    """Verifies that API returns HTTP 400 when liveness check fails."""
    client = TestClient(app)
    mock_service = MagicMock(spec=BiometricService)
    mock_service.verify.return_value = AuthenticationResult(
        success=False,
        matched=False,
        user_id="USR_SPOOF",
        error_code="LIVENESS_CHECK_FAILED",
        message="Biometric authentication rejected: Presentation attack detected (liveness check failed).",
        metadata={"liveness_passed": False, "liveness_score": 0.15},
    )

    app.dependency_overrides[get_biometric_service] = lambda: mock_service
    try:
        response = client.post(
            "/api/v1/auth/verify",
            data={"user_id": "USR_SPOOF"},
            files={"image": ("probe.jpg", b"fake_bytes", "image/jpeg")},
        )
        assert response.status_code == 400
        data = response.json()
        assert "Presentation attack detected" in data["detail"]
    finally:
        app.dependency_overrides.clear()
