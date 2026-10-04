from pathlib import Path
import cv2
import numpy as np
import pytest

from app.biometric.exceptions import (
    InvalidImageError,
    MultipleFacesDetectedError,
    NoFaceDetectedError,
)
from app.biometric.face_engine import FaceEngine
from app.biometric.matching import FaceMatcher
from app.models.biometric import BiometricTemplate
from app.services.biometric_service import BiometricService
from app.storage.local_repository import LocalBiometricRepository

BASE_DIR = Path(__file__).resolve().parent.parent
IMAGE_MALHAR = BASE_DIR / "dataset" / "1_Malhar.jpg"
IMAGE_HARSH = BASE_DIR / "dataset" / "2_Harsh.jpg"


@pytest.fixture(scope="module")
def shared_engine():
    """Initializes FaceEngine once for the test module."""
    engine = FaceEngine()
    engine.initialize()
    return engine


@pytest.fixture
def temp_repo(tmp_path):
    """Provides an isolated clean repository for each test."""
    db_path = tmp_path / "test_templates.json"
    return LocalBiometricRepository(storage_path=db_path, auto_import_legacy=False)


@pytest.fixture
def service(shared_engine, temp_repo):
    """Initializes BiometricService with shared engine and isolated repo."""
    matcher = FaceMatcher(default_threshold=0.85)
    return BiometricService(engine=shared_engine, matcher=matcher, repository=temp_repo)


# ============================================================================
# Test 1: Valid image → face detected
# ============================================================================
def test_valid_image_face_detected(shared_engine):
    assert IMAGE_MALHAR.exists(), f"Sample image {IMAGE_MALHAR} required for test."
    rgb_img = shared_engine.process_image(str(IMAGE_MALHAR))
    faces = shared_engine.detect_faces(rgb_img)

    assert len(faces) >= 1
    assert hasattr(faces[0], "bbox")
    assert faces[0].det_score > 0.60


# ============================================================================
# Test 2: Valid face → embedding generated
# ============================================================================
def test_valid_face_embedding_generated(shared_engine):
    rgb_img = shared_engine.process_image(str(IMAGE_MALHAR))
    faces = shared_engine.detect_faces(rgb_img)
    embedding = shared_engine.generate_embedding(faces[0])

    assert isinstance(embedding, np.ndarray)
    assert embedding.shape == (512,)
    assert pytest.approx(np.linalg.norm(embedding), abs=1e-4) == 1.0


# ============================================================================
# Test 3: Same person's embeddings → positive match
# ============================================================================
def test_same_person_positive_match(service):
    # Enroll user Malhar
    enroll_result = service.enroll(
        user_id="user_malhar",
        image_input=str(IMAGE_MALHAR),
        metadata={"name": "Malhar"}
    )
    assert enroll_result.success is True
    assert enroll_result.matched is True

    # 1:1 Verification of Malhar against Malhar's template
    verify_result = service.verify(
        user_id="user_malhar",
        image_input=str(IMAGE_MALHAR)
    )
    assert verify_result.success is True
    assert verify_result.matched is True
    assert verify_result.user_id == "user_malhar"
    assert verify_result.distance < 0.10  # Identical image yields near-zero distance
    assert verify_result.similarity > 0.95


# ============================================================================
# Test 4: Different person's embeddings → negative match
# ============================================================================
def test_different_person_negative_match(service):
    # Enroll user Malhar
    service.enroll(
        user_id="user_malhar",
        image_input=str(IMAGE_MALHAR),
        metadata={"name": "Malhar"}
    )

    # Attempt to verify Harsh's image against Malhar's identity
    verify_result = service.verify(
        user_id="user_malhar",
        image_input=str(IMAGE_HARSH)
    )

    assert verify_result.success is True
    assert verify_result.matched is False
    assert verify_result.distance > 0.85
    assert verify_result.error_code == "BIOMETRIC_MISMATCH"


# ============================================================================
# Test 5: No face → controlled failure
# ============================================================================
def test_no_face_controlled_failure(service):
    # Create a solid black image with no face
    black_image = np.zeros((400, 400, 3), dtype=np.uint8)

    # 1. Direct engine call must raise NoFaceDetectedError
    with pytest.raises(NoFaceDetectedError):
        service.engine.generate_embedding_from_image(black_image)

    # 2. Service-level enrollment must return structured error without crashing
    enroll_res = service.enroll(user_id="nobody", image_input=black_image)
    assert enroll_res.success is False
    assert enroll_res.matched is False
    assert enroll_res.error_code == "NO_FACE_DETECTED"

    # 3. Service-level verification for enrolled user must return NO_FACE_DETECTED
    service.enroll(user_id="user_enrolled", image_input=str(IMAGE_MALHAR))
    verify_res = service.verify(user_id="user_enrolled", image_input=black_image)
    assert verify_res.success is False
    assert verify_res.matched is False
    assert verify_res.error_code == "NO_FACE_DETECTED"


# ============================================================================
# Test 6: Multiple faces → controlled failure or clearly defined behavior
# ============================================================================
def test_multiple_faces_controlled_failure(service):
    # Horizontally concatenate two face images to create a multi-face test frame
    img1 = cv2.imread(str(IMAGE_MALHAR))
    img2 = cv2.imread(str(IMAGE_HARSH))

    # Resize to same height
    h = 300
    w1 = int(img1.shape[1] * (h / img1.shape[0]))
    w2 = int(img2.shape[1] * (h / img2.shape[0]))
    resized1 = cv2.resize(img1, (w1, h))
    resized2 = cv2.resize(img2, (w2, h))
    multi_face_img = np.hstack([resized1, resized2])

    # Direct engine call with require_single_face=True must raise MultipleFacesDetectedError
    with pytest.raises(MultipleFacesDetectedError):
        service.engine.generate_embedding_from_image(multi_face_img, require_single_face=True)

    # Service enrollment enforces single face and must return controlled error
    enroll_res = service.enroll(user_id="multi_user", image_input=multi_face_img)
    assert enroll_res.success is False
    assert enroll_res.matched is False
    assert enroll_res.error_code == "MULTIPLE_FACES_DETECTED"


# ============================================================================
# Test 7: Invalid input → controlled error
# ============================================================================
def test_invalid_input_controlled_error(service):
    # Enroll a user first so template exists in repository
    service.enroll(user_id="user_err", image_input=str(IMAGE_MALHAR))

    # 1. Non-existent file path
    res1 = service.enroll(user_id="user_err2", image_input="non_existent_file_xyz.jpg")
    assert res1.success is False
    assert res1.error_code == "INVALID_IMAGE"

    # 2. Corrupted byte buffer
    res2 = service.verify(user_id="user_err", image_input=b"corrupted_stream_content")
    assert res2.success is False
    assert res2.error_code == "INVALID_IMAGE"

    # 3. None input to identification
    res3 = service.identify(image_input=None)
    assert res3.success is False
    assert res3.error_code == "INVALID_IMAGE"

