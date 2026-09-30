"""In-memory sliding-window rate limiter — no Redis required.

Uses a per-IP deque of request timestamps. Old entries are pruned on
each check, keeping memory bounded. Thread-safe via a module-level lock.
"""

import logging
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

logger = logging.getLogger("app.security.rate_limiter")

_lock = threading.Lock()
_buckets: dict[str, deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    """Extract the client IP, respecting X-Forwarded-For behind a proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(
    request: Request,
    *,
    scope: str,
    max_requests: int,
    window_seconds: int,
) -> None:
    """Raise 429 if the client exceeds ``max_requests`` within the window.

    Args:
        request: The incoming FastAPI request (used to extract client IP).
        scope: A namespace for the rate limit bucket (e.g. "auth:login").
        max_requests: Maximum allowed requests in the window.
        window_seconds: Sliding window duration in seconds.
    """
    ip = _client_ip(request)
    key = f"{scope}:{ip}"
    now = time.monotonic()
    cutoff = now - window_seconds

    with _lock:
        bucket = _buckets[key]
        # Prune expired entries
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= max_requests:
            logger.warning(
                "Rate limit exceeded: scope=%s, ip=%s, limit=%d/%ds",
                scope,
                ip,
                max_requests,
                window_seconds,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(window_seconds)},
            )
        bucket.append(now)


def reset_buckets() -> None:
    """Clear all rate limit state — only use in tests."""
    with _lock:
        _buckets.clear()
