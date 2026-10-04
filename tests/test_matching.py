import numpy as np
import pytest

from app.biometric.matching import FaceMatcher
from app.models.biometric import BiometricTemplate


@pytest.fixture
def matcher():
    return FaceMatcher(default_threshold=0.85)


@pytest.fixture
def sample_embeddings():
    """Generates two distinct normalized 512-dimensional synthetic embeddings."""
    np.random.seed(42)
    vec1 = np.random.randn(512).astype(np.float32)
    vec1 /= np.linalg.norm(vec1)

    vec2 = np.random.randn(512).astype(np.float32)
    vec2 /= np.linalg.norm(vec2)

    # A slightly perturbed version of vec1 (simulating same person under lighting variance)
    vec1_perturbed = vec1 + np.random.normal(0, 0.02, 512).astype(np.float32)
    vec1_perturbed /= np.linalg.norm(vec1_perturbed)

    return vec1, vec2, vec1_perturbed


def test_distance_and_similarity_identity(matcher, sample_embeddings):
    vec1, _, _ = sample_embeddings
    dist = matcher.calculate_distance(vec1, vec1)
    sim = matcher.calculate_similarity(vec1, vec1)

    assert pytest.approx(dist, abs=1e-5) == 0.0
    assert pytest.approx(sim, abs=1e-5) == 1.0


def test_same_person_positive_match(matcher, sample_embeddings):
    vec1, _, vec1_perturbed = sample_embeddings
    is_match, sim, dist = matcher.compare(vec1, vec1_perturbed)

    assert is_match is True
    assert dist < 0.85
    assert sim > 0.80


def test_different_person_negative_match(matcher, sample_embeddings):
    vec1, vec2, _ = sample_embeddings
    is_match, sim, dist = matcher.compare(vec1, vec2)

    # Random unit vectors in 512-d are nearly orthogonal (L2 dist ~ 1.41, cos sim ~ 0.0)
    assert is_match is False
    assert dist > 1.20
    assert sim < 0.30


def test_configurable_threshold(sample_embeddings):
    vec1, _, vec1_perturbed = sample_embeddings
    dist = np.linalg.norm(vec1 - vec1_perturbed)

    # Strict matcher with threshold tighter than perturbation distance
    strict_matcher = FaceMatcher(default_threshold=dist / 2)
    is_match, _, _ = strict_matcher.compare(vec1, vec1_perturbed)
    assert is_match is False

    # Lenient matcher with threshold larger than perturbation distance
    lenient_matcher = FaceMatcher(default_threshold=dist * 2)
    is_match, _, _ = lenient_matcher.compare(vec1, vec1_perturbed)
    assert is_match is True


def test_find_best_match_1_to_n(matcher, sample_embeddings):
    vec1, vec2, vec1_perturbed = sample_embeddings

    templates = [
        BiometricTemplate(user_id="user_b", embedding=vec2, template_id="tmpl_b"),
        BiometricTemplate(user_id="user_a", embedding=vec1, template_id="tmpl_a"),
    ]

    best_match, sim, dist = matcher.find_best_match(vec1_perturbed, templates)

    assert best_match is not None
    assert best_match.user_id == "user_a"
    assert best_match.template_id == "tmpl_a"
    assert dist < 0.85


def test_find_best_match_unknown_person(matcher, sample_embeddings):
    vec1, vec2, _ = sample_embeddings

    # Query is vec2, candidate list only contains vec1
    templates = [
        BiometricTemplate(user_id="user_a", embedding=vec1, template_id="tmpl_a"),
    ]

    best_match, sim, dist = matcher.find_best_match(vec2, templates)

    # Must reject as unknown because distance exceeds 0.85
    assert best_match is None
    assert dist > 0.85
