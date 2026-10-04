"""
In-Memory Sliding Window Rate Limiter.

Protects biometric endpoints (/verify, /identify, /enroll, /token) from
brute-force enumeration and denial-of-service (CPU exhaustion on ONNX Runtime).
Operates without external dependencies (no Redis required for single-node deployments).
Returns HTTP 429 Too Many Requests with standard RateLimit headers.
"""

from collections import defaultdict
import threading
import time
from typing import Optional
from fastapi import HTTPException, Request, status

from app.config.settings import settings
from app.utils.logging import logger


class InMemorySlidingWindowRateLimiter:
    """
    Thread-safe in-memory sliding window rate limiter tracking request timestamps per client IP.
    Automatically purges expired windows to maintain minimal memory overhead.
    """

    def __init__(self):
        self._lock = threading.Lock()
        # Mapping: endpoint_key -> { client_ip: [timestamp, timestamp, ...] }
        self._windows: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        self._last_cleanup = time.time()

    def _cleanup_stale_entries(self, current_time: float, max_age: float = 300.0) -> None:
        """Periodic garbage collection for IP records older than max_age."""
        if current_time - self._last_cleanup < 60.0:
            return

        for endpoint_dict in self._windows.values():
            stale_ips = []
            for ip, timestamps in endpoint_dict.items():
                # Filter timestamps in-place
                valid_timestamps = [t for t in timestamps if current_time - t <= max_age]
                if valid_timestamps:
                    endpoint_dict[ip] = valid_timestamps
                else:
                    stale_ips.append(ip)
            for ip in stale_ips:
                endpoint_dict.pop(ip, None)

        self._last_cleanup = current_time

    def check(
        self,
        key: str,
        client_ip: str,
        max_requests: int,
        window_seconds: int = 60,
    ) -> tuple[bool, int, int, int]:
        """
        Evaluates whether a request from client_ip is allowed under the sliding window limit.
        
        Returns:
            (allowed, remaining_requests, reset_seconds, limit)
        """
        now = time.time()
        window_start = now - window_seconds

        with self._lock:
            self._cleanup_stale_entries(now, max_age=float(window_seconds * 2))

            timestamps = self._windows[key][client_ip]
            # Retain only timestamps inside the active sliding window
            valid_timestamps = [t for t in timestamps if t > window_start]
            self._windows[key][client_ip] = valid_timestamps

            current_count = len(valid_timestamps)
            if current_count >= max_requests:
                # Rate limit exceeded: calculate retry-after duration based on oldest timestamp
                oldest_timestamp = valid_timestamps[0]
                retry_after = max(1, int(oldest_timestamp + window_seconds - now))
                return False, 0, retry_after, max_requests

            # Allow request and append current timestamp
            valid_timestamps.append(now)
            remaining = max(0, max_requests - len(valid_timestamps))
            return True, remaining, window_seconds, max_requests

    def reset(self) -> None:
        """Clears all rate limit windows (primarily for testing)."""
        with self._lock:
            self._windows.clear()


# Global rate limiter instance
_global_limiter = InMemorySlidingWindowRateLimiter()


def get_client_ip(request: Request) -> str:
    """Extracts client IP address, honoring standard forward headers if present."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # First IP in comma-separated proxy list is original client
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


class RateLimiter:
    """
    FastAPI dependency factory enforcing rate limits on specific routes.
    """

    def __init__(
        self,
        name: str,
        times: int,
        seconds: int = 60,
        limiter: Optional[InMemorySlidingWindowRateLimiter] = None,
    ):
        self.name = name
        self.times = times
        self.seconds = seconds
        self.limiter = limiter or _global_limiter

    async def __call__(self, request: Request) -> None:
        if not settings.rate_limit_enabled:
            return

        client_ip = get_client_ip(request)
        allowed, remaining, retry_after, limit = self.limiter.check(
            key=self.name,
            client_ip=client_ip,
            max_requests=self.times,
            window_seconds=self.seconds,
        )

        # Attach rate limit info to request state for response headers if needed
        request.state.rate_limit_limit = limit
        request.state.rate_limit_remaining = remaining
        request.state.rate_limit_reset = retry_after

        if not allowed:
            logger.warning(
                f"Rate limit exceeded for endpoint '{self.name}' from IP: {client_ip} "
                f"({limit} req/{self.seconds}s). Retry-After: {retry_after}s"
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests for endpoint '{self.name}'. Rate limit exceeded.",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(retry_after),
                },
            )
