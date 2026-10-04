import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.app import app
from app.api.dependencies import get_current_admin
from app.api.rate_limiter import InMemorySlidingWindowRateLimiter, RateLimiter, _global_limiter


@pytest.fixture(autouse=True)
def reset_global_limiter():
    """Ensures rate limiter windows are clean before and after each test."""
    _global_limiter.reset()
    yield
    _global_limiter.reset()


def test_sliding_window_limiter_logic():
    """Unit test for InMemorySlidingWindowRateLimiter tracking and limits."""
    limiter = InMemorySlidingWindowRateLimiter()

    # Allowed for first 3 requests
    allowed, rem, reset_sec, limit = limiter.check("test_endpoint", "192.168.1.1", max_requests=3, window_seconds=60)
    assert allowed is True
    assert rem == 2
    assert limit == 3

    allowed, rem, _, _ = limiter.check("test_endpoint", "192.168.1.1", max_requests=3, window_seconds=60)
    assert allowed is True
    assert rem == 1

    allowed, rem, _, _ = limiter.check("test_endpoint", "192.168.1.1", max_requests=3, window_seconds=60)
    assert allowed is True
    assert rem == 0

    # 4th request must be rejected
    allowed, rem, retry_after, _ = limiter.check("test_endpoint", "192.168.1.1", max_requests=3, window_seconds=60)
    assert allowed is False
    assert rem == 0
    assert retry_after > 0

    # Different IP is not affected
    allowed_other, _, _, _ = limiter.check("test_endpoint", "10.0.0.1", max_requests=3, window_seconds=60)
    assert allowed_other is True


def test_api_rate_limit_exceeded_verify_returns_429():
    """
    Integration test: Simulates excessive requests to /api/v1/auth/verify
    and asserts HTTP 429 Too Many Requests with RateLimit headers.
    """
    client = TestClient(app)

    # Use a small test limiter: 2 requests per minute
    test_limiter = InMemorySlidingWindowRateLimiter()
    strict_rate_limiter = RateLimiter("verify_test", times=2, seconds=60, limiter=test_limiter)

    # Inject dependency override for rate_limit_verify
    from app.api.dependencies import rate_limit_verify
    app.dependency_overrides[rate_limit_verify] = strict_rate_limiter

    try:
        dummy_file = {"image": ("face.jpg", b"fake_bytes", "image/jpeg")}
        # Request 1: Allowed (returns 400 due to empty user_id, proving it passed rate limiter)
        resp1 = client.post("/api/v1/auth/verify", data={"user_id": "   "}, files=dummy_file)
        assert resp1.status_code == 400

        # Request 2: Allowed
        resp2 = client.post("/api/v1/auth/verify", data={"user_id": "   "}, files=dummy_file)
        assert resp2.status_code == 400

        # Request 3: Exceeds rate limit (must return HTTP 429)
        resp3 = client.post("/api/v1/auth/verify", data={"user_id": "   "}, files=dummy_file)
        assert resp3.status_code == 429
        assert "Rate limit exceeded" in resp3.json()["detail"]
        assert "Retry-After" in resp3.headers
        assert resp3.headers.get("X-RateLimit-Remaining") == "0"
        assert int(resp3.headers.get("Retry-After", "0")) > 0
    finally:
        app.dependency_overrides.pop(rate_limit_verify, None)


def test_api_rate_limit_exceeded_identify_returns_429():
    """Integration test: Simulates excessive requests to /api/v1/auth/identify returning HTTP 429."""
    client = TestClient(app)

    test_limiter = InMemorySlidingWindowRateLimiter()
    strict_rate_limiter = RateLimiter("identify_test", times=2, seconds=60, limiter=test_limiter)

    from app.api.dependencies import rate_limit_identify
    app.dependency_overrides[rate_limit_identify] = strict_rate_limiter

    try:
        dummy_file = {"image": ("face.jpg", b"fake_bytes", "image/jpeg")}
        # Requests 1 and 2: Allowed
        client.post("/api/v1/auth/identify", files=dummy_file)
        client.post("/api/v1/auth/identify", files=dummy_file)

        # Request 3: HTTP 429
        resp = client.post("/api/v1/auth/identify", files=dummy_file)
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
    finally:
        app.dependency_overrides.pop(rate_limit_identify, None)


def test_api_rate_limit_exceeded_enroll_returns_429():
    """Integration test: Simulates excessive requests to /api/v1/auth/enroll returning HTTP 429."""
    client = TestClient(app)

    test_limiter = InMemorySlidingWindowRateLimiter()
    strict_rate_limiter = RateLimiter("enroll_test", times=1, seconds=60, limiter=test_limiter)

    from app.api.dependencies import rate_limit_enroll
    app.dependency_overrides[get_current_admin] = lambda: {"username": "admin", "role": "admin"}
    app.dependency_overrides[rate_limit_enroll] = strict_rate_limiter

    try:
        dummy_file = {"image": ("face.jpg", b"fake_bytes", "image/jpeg")}
        # Request 1: Allowed
        resp1 = client.post("/api/v1/auth/enroll", data={"user_id": "   ", "name": "Test"}, files=dummy_file)
        assert resp1.status_code == 400

        # Request 2: Rejected by rate limit
        resp2 = client.post("/api/v1/auth/enroll", data={"user_id": "   ", "name": "Test"}, files=dummy_file)
        assert resp2.status_code == 429
        assert "Retry-After" in resp2.headers
    finally:
        app.dependency_overrides.pop(rate_limit_enroll, None)
        app.dependency_overrides.pop(get_current_admin, None)
