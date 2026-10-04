from typing import Optional, Union
import numpy as np

from app.biometric.embedding import validate_embedding
from app.config.settings import settings
from app.models.biometric import BiometricTemplate, BiometricVerification
from app.utils.logging import logger


class FaceMatcher:
    """
    Mathematical comparison engine for 512-dimensional normalized facial embeddings.

    Matching Logic & Thresholds:
    -----------------------------
    The default threshold (0.85 Euclidean distance) is inherited from the legacy system's
    InsightFace Buffalo_L implementation.
    
    Because the embeddings are L2 unit-normalized (||v|| = 1.0):
      - Euclidean Distance: d = ||a - b||_2
      - Cosine Similarity:  cos(θ) = a · b = 1 - (d^2) / 2
      - At d = 0.85: cos(θ) ≈ 1 - (0.85^2)/2 = 0.63875 (approx 0.64).
      
    NOTE ON THRESHOLD VALIDATION:
    The 0.85 threshold is an operational prototype heuristic and has NOT undergone rigorous
    empirical calibration (such as ROC curve analysis for target False Acceptance Rate / 
    False Rejection Rate). Full biometric calibration is scheduled for Stage 3.
    """

    def __init__(self, default_threshold: Optional[float] = None):
        self.default_threshold = (
            default_threshold
            if default_threshold is not None
            else settings.biometric_match_threshold
        )

    def calculate_distance(
        self,
        embedding_a: Union[np.ndarray, list[float]],
        embedding_b: Union[np.ndarray, list[float]],
    ) -> float:
        """
        Calculates standard Euclidean (L2) distance between two normalized vectors.
        Returns a float >= 0.0. Lower value means closer identity match.
        """
        vec_a = validate_embedding(embedding_a)
        vec_b = validate_embedding(embedding_b)
        dist = float(np.linalg.norm(vec_a - vec_b))
        return dist

    def calculate_similarity(
        self,
        embedding_a: Union[np.ndarray, list[float]],
        embedding_b: Union[np.ndarray, list[float]],
    ) -> float:
        """
        Calculates Cosine Similarity between two vectors: (a · b) / (||a|| ||b||).
        Returns a float between -1.0 and 1.0 (typically 0.0 to 1.0 for face embeddings).
        Higher value means closer identity match.
        """
        vec_a = validate_embedding(embedding_a)
        vec_b = validate_embedding(embedding_b)
        # Dot product for unit-normalized vectors equals cosine similarity
        sim = float(np.dot(vec_a, vec_b))
        # Clamp to [-1.0, 1.0] to guard against minor floating-point inaccuracies
        return max(-1.0, min(1.0, sim))

    def compare(
        self,
        query_embedding: Union[np.ndarray, list[float]],
        stored_embedding: Union[np.ndarray, list[float]],
        threshold: Optional[float] = None,
    ) -> tuple[bool, float, float]:
        """
        Compares two embeddings (1:1 Verification).
        
        Args:
            query_embedding: The probe embedding to verify.
            stored_embedding: The enrolled reference template embedding.
            threshold: Optional custom distance threshold. Defaults to self.default_threshold.

        Returns:
            Tuple: (is_match: bool, similarity: float, distance: float)
        """
        t = threshold if threshold is not None else self.default_threshold
        dist = self.calculate_distance(query_embedding, stored_embedding)
        sim = self.calculate_similarity(query_embedding, stored_embedding)
        is_match = bool(dist < t)
        return is_match, sim, dist

    def find_best_match(
        self,
        query_embedding: Union[np.ndarray, list[float]],
        candidates: list[BiometricTemplate],
        threshold: Optional[float] = None,
    ) -> tuple[Optional[BiometricTemplate], float, float]:
        """
        Compares query embedding against a list of enrolled candidate templates (1:N Identification).
        
        Args:
            query_embedding: The probe embedding.
            candidates: List of enrolled BiometricTemplate instances.
            threshold: Optional custom distance threshold. Defaults to self.default_threshold.

        Returns:
            Tuple of:
              (best_template: BiometricTemplate | None, best_similarity: float, best_distance: float)
        """
        if not candidates:
            return None, 0.0, float("inf")

        t = threshold if threshold is not None else self.default_threshold
        query_vec = validate_embedding(query_embedding)

        # Vectorized batch comparison for high performance
        candidate_matrix = np.stack([c.embedding for c in candidates], axis=0)
        distances = np.linalg.norm(candidate_matrix - query_vec, axis=1)

        min_idx = int(np.argmin(distances))
        best_dist = float(distances[min_idx])
        best_candidate = candidates[min_idx]
        best_sim = self.calculate_similarity(query_vec, best_candidate.embedding)

        logger.debug(
            f"Candidate matching evaluated {len(candidates)} template(s). "
            f"Best distance: {best_dist:.4f} (threshold={t:.4f})"
        )

        if best_dist < t:
            return best_candidate, best_sim, best_dist
        else:
            return None, best_sim, best_dist
