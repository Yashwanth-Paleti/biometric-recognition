from pathlib import Path
import numpy as np
import pytest

from app.biometric.embedding import validate_embedding, create_face_embedding
from app.biometric.exceptions import EmbeddingExtractionError, InvalidImageError
from app.biometric.face_engine import FaceEngine
from app.models.biometric import FaceEmbedding

DATASET_SAMPLE = Path(__file__).resolve().parent.parent / "dataset" / "1_Malhar.jpg"


def test_validate_embedding_valid():
    vec = np.ones(512, dtype=np.float32)
    vec /= np.linalg.norm(vec)
    validated = validate_embedding(vec)
    assert validated.shape == (512,)
    assert validated.dtype == np.float32
    assert pytest.approx(np.linalg.norm(validated), abs=1e-5) == 1.0


def test_validate_embedding_wrong_dimension():
    vec = np.ones(256, dtype=np.float32)
    with pytest.raises(EmbeddingExtractionError, match="Invalid embedding dimension"):
        validate_embedding(vec)


def test_validate_embedding_non_finite():
    vec = np.ones(512, dtype=np.float32)
    vec[10] = np.nan
    with pytest.raises(EmbeddingExtractionError, match="non-finite"):
        validate_embedding(vec)


def test_create_face_embedding():
    vec = np.random.randn(512).astype(np.float32)
    vec /= np.linalg.norm(vec)
    face_emb = create_face_embedding(vec, bbox=[10, 20, 100, 120], score=0.98)
    assert isinstance(face_emb, FaceEmbedding)
    assert face_emb.dimension == 512
    assert len(face_emb.to_list()) == 512


def test_process_image_invalid_inputs():
    engine = FaceEngine()

    # None input
    with pytest.raises(InvalidImageError, match="cannot be None"):
        engine.process_image(None)

    # Empty bytes
    with pytest.raises(InvalidImageError, match="byte stream is empty"):
        engine.process_image(b"")

    # Corrupt bytes
    with pytest.raises(InvalidImageError, match="Failed to decode"):
        engine.process_image(b"not_an_image_data")

    # Nonexistent file
    with pytest.raises(InvalidImageError, match="file not found"):
        engine.process_image("nonexistent_image_path_12345.jpg")


@pytest.mark.skipif(not DATASET_SAMPLE.exists(), reason="Sample dataset image not found")
def test_face_engine_real_extraction():
    engine = FaceEngine()
    engine.initialize()
    embedding = engine.generate_embedding_from_image(str(DATASET_SAMPLE), require_single_face=True)

    assert isinstance(embedding, np.ndarray)
    assert embedding.shape == (512,)
    assert embedding.dtype == np.float32
    assert pytest.approx(np.linalg.norm(embedding), abs=1e-4) == 1.0
