"""Rate limiting middleware."""
import time
from collections import defaultdict
from typing import Dict, Optional, Tuple
from datetime import datetime

from fastapi import Request, HTTPException


class RateLimiter:
    """Simple in-memory rate limiter.

    For production, consider using Redis-based rate limiting.
    """

    def __init__(self, default_limit: int = 60, window_seconds: int = 60):
        self.default_limit = default_limit
        self.window_seconds = window_seconds
        # Store: {key: [(timestamp, count), ...]}
        self._requests: Dict[str, list] = defaultdict(list)

    def _get_key(self, request: Request) -> str:
        """Get rate limit key from request."""
        # Use API key if available, otherwise use IP
        if hasattr(request.state, "api_key") and request.state.api_key:
            return f"key:{request.state.api_key.id}"
        # Get client IP
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}"

    def _get_limit(self, request: Request) -> int:
        """Get rate limit for the request."""
        if hasattr(request.state, "api_key") and request.state.api_key:
            return request.state.api_key.rate_limit_per_minute
        return self.default_limit

    def _clean_old_requests(self, key: str, now: float) -> None:
        """Remove requests outside the current window."""
        cutoff = now - self.window_seconds
        self._requests[key] = [
            (ts, count) for ts, count in self._requests[key]
            if ts > cutoff
        ]

    def _get_current_count(self, key: str) -> int:
        """Get current request count in window."""
        return sum(count for _, count in self._requests[key])

    def check_rate_limit(self, request: Request) -> Tuple[bool, Optional[int]]:
        """Check if request is within rate limit.

        Returns:
            Tuple of (is_allowed, retry_after_seconds)
        """
        key = self._get_key(request)
        limit = self._get_limit(request)
        now = time.time()

        # Clean old requests
        self._clean_old_requests(key, now)

        # Check current count
        current_count = self._get_current_count(key)

        if current_count >= limit:
            # Calculate retry after
            oldest_request = min(ts for ts, _ in self._requests[key]) if self._requests[key] else now
            retry_after = int(oldest_request + self.window_seconds - now) + 1
            return False, max(1, retry_after)

        # Add new request
        self._requests[key].append((now, 1))
        return True, None

    def get_remaining(self, request: Request) -> int:
        """Get remaining requests in current window."""
        key = self._get_key(request)
        limit = self._get_limit(request)
        self._clean_old_requests(key, time.time())
        current_count = self._get_current_count(key)
        return max(0, limit - current_count)


# Global rate limiter instance
rate_limiter = RateLimiter()


async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting middleware for FastAPI."""
    # Skip rate limiting for health check
    if request.url.path.endswith("/health"):
        return await call_next(request)

    is_allowed, retry_after = rate_limiter.check_rate_limit(request)

    if not is_allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "Rate limit exceeded. Please try again later.",
                "retry_after_seconds": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )

    response = await call_next(request)

    # Add rate limit headers
    remaining = rate_limiter.get_remaining(request)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)

    return response
