from datetime import timedelta
import pytest
from fastapi.testclient import TestClient

from app.api.app import app
from app.config.settings import settings
from app.utils.security import create_access_token, hash_password, verify_password


@pytest.fixture
def auth_client():
    """Unauthenticated clean TestClient for verifying authentication behavior."""
    return TestClient(app)


def test_password_hashing_and_verification():
    """Verifies that bcrypt correctly hashes and verifies passwords."""
    password = "SuperSecretAdminPassword123!"
    hashed = hash_password(password)

    assert hashed != password
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False
    assert verify_password("", hashed) is False


def test_token_issue_valid_credentials(auth_client):
    """Verifies that POST /api/v1/auth/token succeeds with valid credentials."""
    response = auth_client.post(
        "/api/v1/auth/token",
        data={
            "username": settings.admin_username,
            "password": settings.admin_password,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"].lower() == "bearer"
    assert data["expires_in"] == settings.jwt_access_token_expire_minutes * 60
    assert len(data["access_token"]) > 20


def test_token_issue_invalid_credentials(auth_client):
    """Verifies that POST /api/v1/auth/token rejects invalid credentials with 401."""
    response = auth_client.post(
        "/api/v1/auth/token",
        data={
            "username": settings.admin_username,
            "password": "WrongPassword999!",
        },
    )
    assert response.status_code == 401
    assert "Incorrect username or password" in response.json()["detail"]


def test_protected_enroll_missing_token(auth_client):
    """Verifies that accessing /api/v1/auth/enroll without a token returns HTTP 401."""
    response = auth_client.post(
        "/api/v1/auth/enroll",
        data={"user_id": "TEST_USER", "name": "Test User"},
        files={"image": ("face.jpg", b"fake", "image/jpeg")},
    )
    assert response.status_code == 401
    assert "Authentication required" in response.json()["detail"]


def test_protected_enroll_invalid_token(auth_client):
    """Verifies that accessing /api/v1/auth/enroll with a malformed token returns HTTP 401."""
    response = auth_client.post(
        "/api/v1/auth/enroll",
        headers={"Authorization": "Bearer this.is.an.invalid.token.signature"},
        data={"user_id": "TEST_USER", "name": "Test User"},
        files={"image": ("face.jpg", b"fake", "image/jpeg")},
    )
    assert response.status_code == 401
    assert "Could not validate credentials" in response.json()["detail"]


def test_protected_enroll_expired_token(auth_client):
    """Verifies that accessing /api/v1/auth/enroll with an expired token returns HTTP 401."""
    expired_token = create_access_token(
        data={"sub": settings.admin_username, "role": "admin"},
        expires_delta=timedelta(seconds=-10),  # expired 10 seconds ago
    )
    response = auth_client.post(
        "/api/v1/auth/enroll",
        headers={"Authorization": f"Bearer {expired_token}"},
        data={"user_id": "TEST_USER", "name": "Test User"},
        files={"image": ("face.jpg", b"fake", "image/jpeg")},
    )
    assert response.status_code == 401
    assert "Token has expired" in response.json()["detail"]


def test_protected_enroll_insufficient_role(auth_client):
    """Verifies that non-admin roles are rejected with HTTP 403 Forbidden."""
    guest_token = create_access_token(
        data={"sub": "guest_user", "role": "guest"},
    )
    response = auth_client.post(
        "/api/v1/auth/enroll",
        headers={"Authorization": f"Bearer {guest_token}"},
        data={"user_id": "TEST_USER", "name": "Test User"},
        files={"image": ("face.jpg", b"fake", "image/jpeg")},
    )
    assert response.status_code == 403
    assert "Administrator privilege required" in response.json()["detail"]


def test_protected_enroll_valid_token_success(auth_client):
    """Verifies that a valid token grants access to /api/v1/auth/enroll."""
    token_resp = auth_client.post(
        "/api/v1/auth/token",
        data={
            "username": settings.admin_username,
            "password": settings.admin_password,
        },
    )
    token = token_resp.json()["access_token"]

    # When valid token is supplied, it passes auth layer and reaches payload validation
    response = auth_client.post(
        "/api/v1/auth/enroll",
        headers={"Authorization": f"Bearer {token}"},
        data={"user_id": "   ", "name": "EmptyIdUser"},  # Empty user_id triggers 400
        files={"image": ("face.jpg", b"fake", "image/jpeg")},
    )
    # Status code is 400 (from payload validation), proving auth succeeded!
    assert response.status_code == 400
    assert "user_id must be a non-empty string" in response.json()["detail"]
