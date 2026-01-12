"""Token bucket rate limiter for API requests."""
import asyncio
import time
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token bucket rate limiter for controlling API request frequency."""

    def __init__(
        self,
        requests_per_second: float = 1.5,
        burst_size: int = 3,
    ):
        """Initialize the rate limiter.

        Args:
            requests_per_second: Maximum sustained request rate.
            burst_size: Maximum number of requests that can be made in a burst.
        """
        self.requests_per_second = requests_per_second
        self.burst_size = burst_size
        self.tokens = float(burst_size)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> None:
        """Acquire tokens, waiting if necessary.

        Args:
            tokens: Number of tokens to acquire.
        """
        async with self._lock:
            await self._wait_for_tokens(tokens)
            self.tokens -= tokens

    async def _wait_for_tokens(self, tokens: int) -> None:
        """Wait until enough tokens are available.

        Args:
            tokens: Number of tokens needed.
        """
        while True:
            self._add_tokens()

            if self.tokens >= tokens:
                return

            # Calculate wait time
            tokens_needed = tokens - self.tokens
            wait_time = tokens_needed / self.requests_per_second
            logger.debug(f"Rate limiter waiting {wait_time:.2f}s for {tokens_needed:.2f} tokens")
            await asyncio.sleep(wait_time)

    def _add_tokens(self) -> None:
        """Add tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_update
        self.last_update = now

        new_tokens = elapsed * self.requests_per_second
        self.tokens = min(self.burst_size, self.tokens + new_tokens)

    def reset(self) -> None:
        """Reset the rate limiter to initial state."""
        self.tokens = float(self.burst_size)
        self.last_update = time.monotonic()


class RequestJitter:
    """Add human-like randomness to request timing."""

    @staticmethod
    async def wait_between_requests(min_seconds: float = 0.5, max_seconds: float = 2.0):
        """Add random delay between requests.

        Args:
            min_seconds: Minimum delay.
            max_seconds: Maximum delay.
        """
        import random
        delay = random.uniform(min_seconds, max_seconds)
        await asyncio.sleep(delay)

    @staticmethod
    async def wait_between_pages(min_seconds: float = 1.0, max_seconds: float = 3.0):
        """Add longer delay between pagination requests.

        Args:
            min_seconds: Minimum delay.
            max_seconds: Maximum delay.
        """
        import random
        delay = random.uniform(min_seconds, max_seconds)
        await asyncio.sleep(delay)

    @staticmethod
    async def wait_session_start(min_seconds: float = 2.0, max_seconds: float = 5.0):
        """Add delay at session start to simulate app loading.

        Args:
            min_seconds: Minimum delay.
            max_seconds: Maximum delay.
        """
        import random
        delay = random.uniform(min_seconds, max_seconds)
        await asyncio.sleep(delay)
