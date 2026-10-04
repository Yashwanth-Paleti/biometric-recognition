import numpy as np
from app.models.biometric import FaceEmbedding
from app.biometric.exceptions import EmbeddingExtractionError

EXPECTED_EMBEDDING_DIM = 512

def validate_embedding(embedding: np.ndarray | list[float]) -> np.ndarray:
    """
    Validates and standardizes a 512-dimensional face embedding.
    Ensures vector is 1D, float32, normalized, and correctly shaped.
    """
    if embedding is None:
        raise EmbeddingExtractionError("Embedding cannot be None.")
        
    if not isinstance(embedding, np.ndarray):
        try:
            embedding = np.array(embedding, dtype=np.float32)
        except Exception as e:
            raise EmbeddingExtractionError(f"Cannot convert embedding to numpy array: {e}")
            
    if embedding.ndim > 1:
        embedding = embedding.flatten()
        
    if embedding.shape[0] != EXPECTED_EMBEDDING_DIM:
        raise EmbeddingExtractionError(
            f"Invalid embedding dimension: expected {EXPECTED_EMBEDDING_DIM}, got {embedding.shape[0]}"
        )
        
    # Check for NaN or Inf
    if not np.all(np.isfinite(embedding)):
        raise EmbeddingExtractionError("Embedding contains non-finite values (NaN or Inf).")
        
    # Normalize if not unit length
    norm = np.linalg.norm(embedding)
    if norm > 0 and not np.isclose(norm, 1.0, atol=1e-3):
        embedding = embedding / norm
        
    return embedding.astype(np.float32)


def create_face_embedding(
    vector: np.ndarray,
    bbox: list[int] | None = None,
    score: float | None = None
) -> FaceEmbedding:
    """Factory helper to construct a validated FaceEmbedding domain object."""
    valid_vec = validate_embedding(vector)
    return FaceEmbedding(
        vector=valid_vec,
        bbox=bbox,
        detection_score=score
    )
