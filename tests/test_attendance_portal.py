import uuid
from datetime import datetime, timezone, date
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.app import app
from app.api.dependencies import get_biometric_service
from app.database.connection import get_db, get_session_factory
from app.database.models import AttendanceModel, BiometricTemplateModel, UserModel
from app.models.biometric import AuthenticationResult
from app.services.attendance_service import AttendanceService
from app.services.biometric_service import BiometricService
from app.utils.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

DUMMY_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"


@pytest.fixture
def client():
    """TestClient instance for FastAPI application."""
    return TestClient(app)


@pytest.fixture
def db_session():
    """Provides a managed database session for unit tests with cleanup."""
    session_factory = get_session_factory()
    session = session_factory()
    test_user_ids = []

    yield session, test_user_ids

    # Teardown: Clean up any test records created during testing
    try:
        for uid in test_user_ids:
            session.query(AttendanceModel).filter(AttendanceModel.user_id == uid).delete()
            session.query(BiometricTemplateModel).filter(BiometricTemplateModel.user_id == uid).delete()
            session.query(UserModel).filter(UserModel.user_id == uid).delete()
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


# ============================================================================
# 1. Student Registration Success
# ============================================================================
def test_student_registration_success(client, db_session):
    session, test_user_ids = db_session
    student_id = f"TEST_STU_{uuid.uuid4().hex[:6].upper()}"
    test_user_ids.append(student_id)

    mock_bio = MagicMock(spec=BiometricService)
    mock_bio.enroll.side_effect = [
        AuthenticationResult(success=True, matched=True, user_id=student_id, message="Enrolled 1"),
        AuthenticationResult(success=True, matched=True, user_id=student_id, message="Enrolled 2"),
    ]
    app.dependency_overrides[get_biometric_service] = lambda: mock_bio

    try:
        response = client.post(
            "/api/v1/students/register",
            data={
                "name": "Yashwanth Paleti",
                "student_id": student_id,
                "email": f"{student_id.lower()}@test.edu",
                "password": "SecurePassword123!",
                "confirm_password": "SecurePassword123!",
            },
            files={
                "image1": ("face1.jpg", DUMMY_JPEG, "image/jpeg"),
                "image2": ("face2.jpg", DUMMY_JPEG, "image/jpeg"),
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["student_id"] == student_id
        assert data["name"] == "Yashwanth Paleti"

        # Verify database record
        user = session.query(UserModel).filter(UserModel.user_id == student_id).first()
        assert user is not None
        assert user.role == "student"
        assert user.password_hash is not None
    finally:
        app.dependency_overrides.pop(get_biometric_service, None)


# ============================================================================
# 2. Duplicate Student ID
# ============================================================================
def test_registration_duplicate_student_id(client, db_session):
    session, test_user_ids = db_session
    student_id = f"TEST_DUP_{uuid.uuid4().hex[:6].upper()}"
    test_user_ids.append(student_id)

    # Pre-seed user in database
    existing_user = UserModel(
        user_id=student_id,
        name="Existing Student",
        email=f"{student_id.lower()}@test.edu",
        password_hash=hash_password("Pass123!"),
        role="student",
        status="active",
    )
    session.add(existing_user)
    session.commit()

    mock_bio = MagicMock(spec=BiometricService)
    app.dependency_overrides[get_biometric_service] = lambda: mock_bio

    try:
        response = client.post(
            "/api/v1/students/register",
            data={
                "name": "Duplicate Student",
                "student_id": student_id,
                "email": f"other_{student_id.lower()}@test.edu",
                "password": "Password123!",
                "confirm_password": "Password123!",
            },
            files={
                "image1": ("face1.jpg", DUMMY_JPEG, "image/jpeg"),
                "image2": ("face2.jpg", DUMMY_JPEG, "image/jpeg"),
            },
        )
        assert response.status_code == 400
        assert "already registered" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_biometric_service, None)


# ============================================================================
# 3. Duplicate Email
# ============================================================================
def test_registration_duplicate_email(client, db_session):
    session, test_user_ids = db_session
    student_id1 = f"STU_EMAIL_A_{uuid.uuid4().hex[:5].upper()}"
    student_id2 = f"STU_EMAIL_B_{uuid.uuid4().hex[:5].upper()}"
    shared_email = f"shared_{uuid.uuid4().hex[:5]}@test.edu"
    test_user_ids.extend([student_id1, student_id2])

    existing_user = UserModel(
        user_id=student_id1,
        name="First Student",
        email=shared_email,
        password_hash=hash_password("Pass123!"),
        role="student",
        status="active",
    )
    session.add(existing_user)
    session.commit()

    mock_bio = MagicMock(spec=BiometricService)
    app.dependency_overrides[get_biometric_service] = lambda: mock_bio

    try:
        response = client.post(
            "/api/v1/students/register",
            data={
                "name": "Second Student",
                "student_id": student_id2,
                "email": shared_email,
                "password": "Password123!",
                "confirm_password": "Password123!",
            },
            files={
                "image1": ("face1.jpg", DUMMY_JPEG, "image/jpeg"),
                "image2": ("face2.jpg", DUMMY_JPEG, "image/jpeg"),
            },
        )
        assert response.status_code == 400
        assert "email" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_biometric_service, None)


# ============================================================================
# 4. Password Hashing Stored Securely
# ============================================================================
def test_password_hashing_stored_securely(client, db_session):
    session, test_user_ids = db_session
    student_id = f"STU_HASH_{uuid.uuid4().hex[:5].upper()}"
    test_user_ids.append(student_id)
    raw_pass = "MySecretPass_999!"

    hashed = hash_password(raw_pass)
    assert hashed.startswith("$2b$")
    assert raw_pass not in hashed
    assert verify_password(raw_pass, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


# ============================================================================
# 5. Student Login Success
# ============================================================================
def test_student_login_success(client, db_session):
    session, test_user_ids = db_session
    student_id = f"STU_LOGIN_{uuid.uuid4().hex[:5].upper()}"
    test_user_ids.append(student_id)
    raw_pass = "ValidPass123!"

    user = UserModel(
        user_id=student_id,
        name="Login Student",
        email=f"{student_id.lower()}@test.edu",
        password_hash=hash_password(raw_pass),
        role="student",
        status="active",
    )
    session.add(user)
    session.commit()

    # Login via student_id
    response = client.post(
        "/api/v1/students/login",
        json={"identifier": student_id, "password": raw_pass},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["student_id"] == student_id
    assert data["role"] == "student"

    # Login via email
    response_email = client.post(
        "/api/v1/students/login",
        json={"identifier": f"{student_id.lower()}@test.edu", "password": raw_pass},
    )
    assert response_email.status_code == 200
    assert "access_token" in response_email.json()


# ============================================================================
# 6. Student Login Failure
# ============================================================================
def test_student_login_failure(client, db_session):
    session, test_user_ids = db_session
    student_id = f"STU_FAIL_{uuid.uuid4().hex[:5].upper()}"
    test_user_ids.append(student_id)

    user = UserModel(
        user_id=student_id,
        name="Fail Student",
        password_hash=hash_password("CorrectPassword!"),
        role="student",
        status="active",
    )
    session.add(user)
    session.commit()

    # Wrong password
    res1 = client.post(
        "/api/v1/students/login",
        json={"identifier": student_id, "password": "WrongPassword!"},
    )
    assert res1.status_code == 401

    # Non-existent user
    res2 = client.post(
        "/api/v1/students/login",
        json={"identifier": "NON_EXISTENT_ID_999", "password": "AnyPassword!"},
    )
    assert res2.status_code == 401


# ============================================================================
# 7. Student JWT Generation and Claims
# ============================================================================
def test_student_jwt_generation_claims():
    student_id = "STU_JWT_001"
    token = create_access_token({
        "sub": student_id,
        "role": "student",
        "name": "JWT Test Student",
    })
    payload = decode_access_token(token)
    assert payload["sub"] == student_id
    assert payload["role"] == "student"
    assert payload["name"] == "JWT Test Student"
    assert "exp" in payload
    assert "iat" in payload


# ============================================================================
# 8. Student-Only Authorization
# ============================================================================
def test_student_only_authorization(client, db_session):
    session, test_user_ids = db_session
    student_id = f"STU_AUTH_{uuid.uuid4().hex[:5].upper()}"
    test_user_ids.append(student_id)

    user = UserModel(
        user_id=student_id,
        name="Auth Test Student",
        role="student",
        status="active",
    )
    session.add(user)
    session.commit()

    student_token = create_access_token({"sub": student_id, "role": "student"})
    admin_token = create_access_token({"sub": "admin", "role": "admin"})

    # 1. Valid student token -> 200 OK
    res_ok = client.get(
        "/api/v1/students/me",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert res_ok.status_code == 200
    assert res_ok.json()["student_id"] == student_id

    # 2. Admin token trying to access student endpoint -> 403 Forbidden
    res_admin = client.get(
        "/api/v1/students/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_admin.status_code == 403

    # 3. Missing token -> 401 Unauthorized
    res_missing = client.get("/api/v1/students/me")
    assert res_missing.status_code == 401


# ============================================================================
# 9. Admin Authorization Still Works
# ============================================================================
def test_admin_authorization_still_works(client):
    admin_token = create_access_token({"sub": "admin", "role": "admin"})
    student_token = create_access_token({"sub": "STU_001", "role": "student"})

    mock_bio = MagicMock(spec=BiometricService)
    mock_bio.enroll.return_value = AuthenticationResult(
        success=True, matched=True, user_id="ADM_TEST", message="Enrolled"
    )
    app.dependency_overrides[get_biometric_service] = lambda: mock_bio

    try:
        # Admin can access /auth/enroll
        res_admin = client.post(
            "/api/v1/auth/enroll",
            headers={"Authorization": f"Bearer {admin_token}"},
            data={"user_id": "ADM_TEST", "name": "Admin Enroll Test"},
            files={"image": ("face.jpg", DUMMY_JPEG, "image/jpeg")},
        )
        assert res_admin.status_code == 201

        # Student token rejected from /auth/enroll with 403
        res_student = client.post(
            "/api/v1/auth/enroll",
            headers={"Authorization": f"Bearer {student_token}"},
            data={"user_id": "ADM_TEST", "name": "Admin Enroll Test"},
            files={"image": ("face.jpg", DUMMY_JPEG, "image/jpeg")},
        )
        assert res_student.status_code == 403
    finally:
        app.dependency_overrides.pop(get_biometric_service, None)


# ============================================================================
# 10. Attendance Success
# ============================================================================
def test_attendance_marking_success(client, db_session):
    session, test_user_ids = db_session
    student_id = f"STU_ATT_{uuid.uuid4().hex[:5].upper()}"
    test_user_ids.append(student_id)

    user = UserModel(
        user_id=student_id,
        name="Attendance Student",
        role="student",
        status="active",
    )
    session.add(user)
    session.commit()

    mock_bio = MagicMock(spec=BiometricService)
    mock_bio.identify.return_value = AuthenticationResult(
        success=True,
        matched=True,
        user_id=student_id,
        similarity=0.92,
        distance=0.40,
        message="Face verified",
    )
    app.dependency_overrides[get_biometric_service] = lambda: mock_bio

    try:
        res = client.post(
            "/api/v1/attendance/mark",
            files={"image": ("probe.jpg", DUMMY_JPEG, "image/jpeg")},
            data={"device_id": "TEST_GATE_1"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["authenticated"] is True
        assert data["user_id"] == student_id
        assert data["name"] == "Attendance Student"
        assert data["status"] == "Present"
        assert data["already_marked"] is False

        # Verify record in DB
        today = datetime.now(timezone.utc).date()
        rec = session.query(AttendanceModel).filter(
            AttendanceModel.user_id == student_id,
            AttendanceModel.attendance_date == today,
        ).first()
        assert rec is not None
        assert rec.status == "Present"
    finally:
        app.dependency_overrides.pop(get_biometric_service, None)


# ============================================================================
# 11. Attendance Unknown Face
# ============================================================================
def test_attendance_marking_unknown_face(client, db_session):
    session, test_user_ids = db_session

    mock_bio = MagicMock(spec=BiometricService)
    mock_bio.identify.return_value = AuthenticationResult(
        success=False,
        matched=False,
        user_id=None,
        message="No matching identity found",
        error_code="NO_MATCH",
    )
    app.dependency_overrides[get_biometric_service] = lambda: mock_bio

    try:
        res = client.post(
            "/api/v1/attendance/mark",
            files={"image": ("unknown.jpg", DUMMY_JPEG, "image/jpeg")},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is False
        assert data["authenticated"] is False
        assert data["user_id"] is None
        assert "no matching identity" in data["message"].lower()
    finally:
        app.dependency_overrides.pop(get_biometric_service, None)


# ============================================================================
# 12. Duplicate Attendance Same Day Prevention
# ============================================================================
def test_duplicate_attendance_same_day(client, db_session):
    session, test_user_ids = db_session
    student_id = f"STU_DUP_ATT_{uuid.uuid4().hex[:5].upper()}"
    test_user_ids.append(student_id)

    user = UserModel(
        user_id=student_id,
        name="Duplicate Att Student",
        role="student",
        status="active",
    )
    session.add(user)
    session.commit()

    mock_bio = MagicMock(spec=BiometricService)
    mock_bio.identify.return_value = AuthenticationResult(
        success=True,
        matched=True,
        user_id=student_id,
        similarity=0.91,
        distance=0.42,
    )
    app.dependency_overrides[get_biometric_service] = lambda: mock_bio

    try:
        # First attendance mark -> Success
        res1 = client.post(
            "/api/v1/attendance/mark",
            files={"image": ("probe.jpg", DUMMY_JPEG, "image/jpeg")},
        )
        assert res1.status_code == 200
        assert res1.json()["success"] is True

        # Second attendance mark on same day -> Prevented
        res2 = client.post(
            "/api/v1/attendance/mark",
            files={"image": ("probe.jpg", DUMMY_JPEG, "image/jpeg")},
        )
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["success"] is False
        assert data2["already_marked"] is True
        assert "already marked today" in data2["message"].lower()

        # Check DB only contains 1 attendance record
        today = datetime.now(timezone.utc).date()
        count = session.query(AttendanceModel).filter(
            AttendanceModel.user_id == student_id,
            AttendanceModel.attendance_date == today,
        ).count()
        assert count == 1
    finally:
        app.dependency_overrides.pop(get_biometric_service, None)


# ============================================================================
# 13. Dashboard Retrieval
# ============================================================================
def test_student_dashboard_retrieval(client, db_session):
    session, test_user_ids = db_session
    student_id = f"STU_DASH_{uuid.uuid4().hex[:5].upper()}"
    test_user_ids.append(student_id)

    user = UserModel(
        user_id=student_id,
        name="Dashboard Student",
        email=f"{student_id.lower()}@test.edu",
        role="student",
        status="active",
    )
    session.add(user)
    session.commit()

    # Add an attendance record
    att = AttendanceModel(
        user_id=student_id,
        attendance_date=date(2026, 10, 4),
        marked_at=datetime(2026, 10, 4, 10, 42, tzinfo=timezone.utc),
        status="Present",
        recognition_similarity=0.94,
        recognition_distance=0.35,
        device_id="GATE_WEST",
    )
    session.add(att)
    session.commit()

    token = create_access_token({"sub": student_id, "role": "student"})
    res = client.get(
        "/api/v1/students/attendance",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["student_id"] == student_id
    assert data["name"] == "Dashboard Student"
    assert data["present_count"] == 1
    assert data["attendance_percentage"] == 100.0
    assert len(data["history"]) == 1
    assert data["history"][0]["status"] == "Present"


# ============================================================================
# 14. Student Cannot Access Another Student's Dashboard
# ============================================================================
def test_student_cannot_access_another_student_dashboard(client, db_session):
    session, test_user_ids = db_session
    student_a = f"STU_A_{uuid.uuid4().hex[:5].upper()}"
    student_b = f"STU_B_{uuid.uuid4().hex[:5].upper()}"
    test_user_ids.extend([student_a, student_b])

    user_a = UserModel(user_id=student_a, name="Alice", role="student", status="active")
    user_b = UserModel(user_id=student_b, name="Bob", role="student", status="active")
    session.add_all([user_a, user_b])
    session.commit()

    # Token belongs to student A
    token_a = create_access_token({"sub": student_a, "role": "student"})

    # When querying attendance, student A receives only student A's data
    res = client.get(
        "/api/v1/students/attendance",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res.status_code == 200
    assert res.json()["student_id"] == student_a
    assert res.json()["name"] == "Alice"
    assert res.json()["student_id"] != student_b


# ============================================================================
# 15. Empty Attendance History
# ============================================================================
def test_empty_attendance_history(client, db_session):
    session, test_user_ids = db_session
    student_id = f"STU_EMPTY_{uuid.uuid4().hex[:5].upper()}"
    test_user_ids.append(student_id)

    user = UserModel(user_id=student_id, name="New Enrolled", role="student", status="active")
    session.add(user)
    session.commit()

    token = create_access_token({"sub": student_id, "role": "student"})
    res = client.get(
        "/api/v1/students/attendance",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["attendance_percentage"] == 0.0
    assert data["present_count"] == 0
    assert data["total_sessions"] == 0
    assert data["last_attendance"] is None
    assert data["history"] == []


# ============================================================================
# 16. Attendance Percentage Calculation
# ============================================================================
def test_attendance_percentage_calculation():
    # 0 sessions
    stats_empty = AttendanceService.get_student_attendance_stats
    # Test formula directly with mock session
    mock_db = MagicMock()
    mock_user = UserModel(user_id="CALC_01", name="Calc User", email=None, role="student")
    mock_db.query().filter().first.return_value = mock_user

    # 0 records
    mock_db.query().filter().order_by().all.return_value = []
    res_0 = AttendanceService.get_student_attendance_stats("CALC_01", mock_db)
    assert res_0.attendance_percentage == 0.0
    assert res_0.present_count == 0

    # 1 present record
    mock_rec1 = AttendanceModel(
        id=str(uuid.uuid4()),
        user_id="CALC_01",
        attendance_date=date(2026, 10, 4),
        marked_at=datetime.now(timezone.utc),
        status="Present",
    )
    mock_db.query().filter().order_by().all.return_value = [mock_rec1]
    res_1 = AttendanceService.get_student_attendance_stats("CALC_01", mock_db)
    assert res_1.attendance_percentage == 100.0
    assert res_1.present_count == 1


# ============================================================================
# 17. Frontend Pages Served Successfully
# ============================================================================
def test_frontend_routes_served(client):
    for path in ["/register", "/login", "/dashboard", "/attendance"]:
        res = client.get(path)
        assert res.status_code == 200
        assert "text/html" in res.headers.get("content-type", "")

    # Root redirect
    res_root = client.get("/", follow_redirects=False)
    assert res_root.status_code in (302, 307)
    assert res_root.headers.get("location") == "/attendance"
