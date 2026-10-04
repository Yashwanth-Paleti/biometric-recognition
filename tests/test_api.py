from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from app.api.app import app
from app.api.dependencies import get_biometric_service, get_current_admin
from app.models.biometric import AuthenticationResult
from app.services.biometric_service import BiometricService
from app.storage.local_repository import LocalBiometricRepository

BASE_DIR = Path(__file__).resolve().parent.parent
IMAGE_MALHAR = BASE_DIR / "dataset" / "1_Malhar.jpg"
IMAGE_HARSH = BASE_DIR / "dataset" / "2_Harsh.jpg"


@pytest.fixture
def client():
    """Provides a TestClient for the FastAPI app with authenticated admin dependency."""
    app.dependency_overrides[get_current_admin] = lambda: {"username": "admin", "role": "admin"}
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_admin, None)



# ============================================================================
# Health Check Tests
# ============================================================================
def test_health_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "storage_backend" in data


# ============================================================================
# Enrollment API Tests
# ============================================================================
def test_enroll_success(client):
    mock_service = MagicMock(spec=BiometricService)
    mock_service.enroll.return_value = AuthenticationResult(
        success=True,
        matched=True,
        user_id="USR_001",
        message="Biometric template successfully enrolled for user 'USR_001'.",
        metadata={"template_id": "tmpl-uuid-1234"},
    )

    app.dependency_overrides[get_biometric_service] = lambda: mock_service
    try:
        response = client.post(
            "/api/v1/auth/enroll",
            data={"user_id": "USR_001", "name": "Yashwanth"},
            files={"image": ("face.jpg", b"\xff\xd8\xff\xe0dummy_jpeg", "image/jpeg")},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["user_id"] == "USR_001"
        assert data["template_id"] == "tmpl-uuid-1234"
        assert "message" in data
        # CRITICAL: Verify raw embedding is never returned
        assert "embedding" not in data
        assert "vector" not in data
    finally:
        app.dependency_overrides.clear()


def test_enroll_missing_fields(client):
    # Missing user_id
    response = client.post(
        "/api/v1/auth/enroll",
        data={"name": "Yashwanth"},
        files={"image": ("face.jpg", b"fake", "image/jpeg")},
    )
    assert response.status_code == 422

    # Empty user_id
    response2 = client.post(
        "/api/v1/auth/enroll",
        data={"user_id": "   ", "name": "Yashwanth"},
        files={"image": ("face.jpg", b"fake", "image/jpeg")},
    )
    assert response2.status_code == 400


def test_enroll_no_face_detected(client):
    mock_service = MagicMock(spec=BiometricService)
    mock_service.enroll.return_value = AuthenticationResult(
        success=False,
        matched=False,
        user_id="USR_002",
        error_code="NO_FACE_DETECTED",
        message="Enrollment failed: No face detected in the provided image.",
    )

    app.dependency_overrides[get_biometric_service] = lambda: mock_service
    try:
        response = client.post(
            "/api/v1/auth/enroll",
            data={"user_id": "USR_002", "name": "Ghost"},
            files={"image": ("noface.jpg", b"dummy_content", "image/jpeg")},
        )
        assert response.status_code == 400
        assert "No face detected" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_enroll_multiple_faces_detected(client):
    mock_service = MagicMock(spec=BiometricService)
    mock_service.enroll.return_value = AuthenticationResult(
        success=False,
        matched=False,
        user_id="USR_003",
        error_code="MULTIPLE_FACES_DETECTED",
        message="Multiple faces detected. Exactly one face is required.",
    )

    app.dependency_overrides[get_biometric_service] = lambda: mock_service
    try:
        response = client.post(
            "/api/v1/auth/enroll",
            data={"user_id": "USR_003", "name": "Crowd"},
            files={"image": ("crowd.jpg", b"dummy_content", "image/jpeg")},
        )
        assert response.status_code == 400
        assert "Multiple faces" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_enroll_invalid_image_type(client):
    response = client.post(
        "/api/v1/auth/enroll",
        data={"user_id": "USR_004", "name": "BadFile"},
        files={"image": ("doc.txt", b"some plain text", "text/plain")},
    )
    assert response.status_code == 400
    assert "Unsupported image media type" in response.json()["detail"]


# ============================================================================
# Verification (1:1) API Tests
# ============================================================================
def test_verify_success(client):
    mock_service = MagicMock(spec=BiometricService)
    mock_service.verify.return_value = AuthenticationResult(
        success=True,
        matched=True,
        user_id="USR_001",
        similarity=0.915,
        distance=0.412,
        threshold=0.85,
        message="Identity verified for user 'USR_001'.",
    )

    app.dependency_overrides[get_biometric_service] = lambda: mock_service
    try:
        response = client.post(
            "/api/v1/auth/verify",
            data={"user_id": "USR_001", "threshold": 0.85},
            files={"image": ("probe.jpg", b"probe_data", "image/jpeg")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is True
        assert data["user_id"] == "USR_001"
        assert abs(data["similarity"] - 0.915) < 1e-3
        assert abs(data["distance"] - 0.412) < 1e-3
        assert "Identity verified" in data["message"]
        # CRITICAL: Verify raw embedding is never exposed
        assert "embedding" not in data
        assert "vector" not in data
    finally:
        app.dependency_overrides.clear()


def test_verify_mismatch(client):
    mock_service = MagicMock(spec=BiometricService)
    mock_service.verify.return_value = AuthenticationResult(
        success=True,
        matched=False,
        user_id="USR_001",
        similarity=0.450,
        distance=1.049,
        threshold=0.85,
        error_code="BIOMETRIC_MISMATCH",
        message="Face does not match enrolled template for user 'USR_001'.",
    )

    app.dependency_overrides[get_biometric_service] = lambda: mock_service
    try:
        response = client.post(
            "/api/v1/auth/verify",
            data={"user_id": "USR_001"},
            files={"image": ("imposter.jpg", b"imposter_data", "image/jpeg")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False
        assert data["user_id"] == "USR_001"
        assert "does not match" in data["message"]
    finally:
        app.dependency_overrides.clear()


def test_verify_user_not_found(client):
    mock_service = MagicMock(spec=BiometricService)
    mock_service.verify.return_value = AuthenticationResult(
        success=False,
        matched=False,
        user_id="UNKNOWN_USER",
        error_code="USER_NOT_ENROLLED",
        message="No enrolled biometric templates found for user 'UNKNOWN_USER'.",
    )

    app.dependency_overrides[get_biometric_service] = lambda: mock_service
    try:
        response = client.post(
            "/api/v1/auth/verify",
            data={"user_id": "UNKNOWN_USER"},
            files={"image": ("face.jpg", b"dummy", "image/jpeg")},
        )
        assert response.status_code == 404
        assert "No enrolled biometric templates" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


# ============================================================================
# Identification (1:N) API Tests
# ============================================================================
def test_identify_success(client):
    mock_service = MagicMock(spec=BiometricService)
    mock_service.identify.return_value = AuthenticationResult(
        success=True,
        matched=True,
        user_id="USR_001",
        similarity=0.912,
        distance=0.419,
        threshold=0.85,
        message="Identity confirmed as 'USR_001'.",
    )

    app.dependency_overrides[get_biometric_service] = lambda: mock_service
    try:
        response = client.post(
            "/api/v1/auth/identify",
            files={"image": ("probe.jpg", b"probe_data", "image/jpeg")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is True
        assert data["user_id"] == "USR_001"
        assert abs(data["similarity"] - 0.912) < 1e-3
        assert data["message"] == "Identity identified"
        assert "embedding" not in data
    finally:
        app.dependency_overrides.clear()


def test_identify_unknown_person(client):
    mock_service = MagicMock(spec=BiometricService)
    mock_service.identify.return_value = AuthenticationResult(
        success=True,
        matched=False,
        user_id=None,
        similarity=0.34,
        distance=1.15,
        threshold=0.85,
        error_code="NO_MATCH",
        message="No matching identity found for the provided face.",
    )

    app.dependency_overrides[get_biometric_service] = lambda: mock_service
    try:
        response = client.post(
            "/api/v1/auth/identify",
            files={"image": ("stranger.jpg", b"stranger_data", "image/jpeg")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False
        assert data["user_id"] is None
        assert data["message"] == "No matching identity found"
    finally:
        app.dependency_overrides.clear()


def test_identify_no_face(client):
    mock_service = MagicMock(spec=BiometricService)
    mock_service.identify.return_value = AuthenticationResult(
        success=False,
        matched=False,
        user_id=None,
        error_code="NO_FACE_DETECTED",
        message="Identification failed: No face detected in the image.",
    )

    app.dependency_overrides[get_biometric_service] = lambda: mock_service
    try:
        response = client.post(
            "/api/v1/auth/identify",
            files={"image": ("noface.jpg", b"data", "image/jpeg")},
        )
        assert response.status_code == 400
        assert "No face detected" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


# ============================================================================
# End-to-End Real Pipeline Test with Sample Image
# ============================================================================
def test_real_pipeline_api_enroll_verify_identify(tmp_path, client):
    """
    Tests full API lifecycle (Enroll -> 1:1 Verify -> 1:N Identify)
    with a real image from dataset/ using an isolated local repository.
    """
    if not IMAGE_MALHAR.exists():
        pytest.skip(f"Test image not found at {IMAGE_MALHAR}")

    repo_file = tmp_path / "test_api_db.json"
    isolated_repo = LocalBiometricRepository(storage_path=repo_file, auto_import_legacy=False)
    real_service = BiometricService(repository=isolated_repo)

    app.dependency_overrides[get_biometric_service] = lambda: real_service
    try:
        with open(IMAGE_MALHAR, "rb") as f:
            img_bytes = f.read()

        # 1. Enroll Malhar
        enroll_resp = client.post(
            "/api/v1/auth/enroll",
            data={"user_id": "MALHAR_01", "name": "Malhar Bhatt"},
            files={"image": ("1_Malhar.jpg", img_bytes, "image/jpeg")},
        )
        assert enroll_resp.status_code == 201
        assert enroll_resp.json()["user_id"] == "MALHAR_01"

        # 2. 1:1 Verify Malhar
        verify_resp = client.post(
            "/api/v1/auth/verify",
            data={"user_id": "MALHAR_01"},
            files={"image": ("1_Malhar.jpg", img_bytes, "image/jpeg")},
        )
        assert verify_resp.status_code == 200
        v_data = verify_resp.json()
        assert v_data["authenticated"] is True
        assert v_data["user_id"] == "MALHAR_01"
        assert v_data["distance"] < 0.20  # Identical image should have very low distance

        # 3. 1:N Identify Malhar
        ident_resp = client.post(
            "/api/v1/auth/identify",
            files={"image": ("1_Malhar.jpg", img_bytes, "image/jpeg")},
        )
        assert ident_resp.status_code == 200
        i_data = ident_resp.json()
        assert i_data["authenticated"] is True
        assert i_data["user_id"] == "MALHAR_01"

        # 4. Verify against a non-enrolled user (expect 404)
        not_found_resp = client.post(
            "/api/v1/auth/verify",
            data={"user_id": "NON_EXISTENT"},
            files={"image": ("1_Malhar.jpg", img_bytes, "image/jpeg")},
        )
        assert not_found_resp.status_code == 404

    finally:
        app.dependency_overrides.clear()
