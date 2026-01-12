"""Async HTTP client with retry logic and rate limiting."""
import httpx
import asyncio
import logging
from typing import Dict, Any, Optional
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from .exceptions import (
    RateLimitError,
    APIError,
    NetworkError,
    AuthenticationError,
)
from .rate_limiter import RateLimiter, RequestJitter
from .fingerprint import DeviceFingerprint
from src.config.settings import settings

logger = logging.getLogger(__name__)


class AsyncAPIClient:
    """Async HTTP client with retry logic, rate limiting, and anti-detection."""

    def __init__(
        self,
        base_url: str,
        rate_limiter: Optional[RateLimiter] = None,
        fingerprint: Optional[DeviceFingerprint] = None,
        timeout: float = 30.0,
    ):
        """Initialize the API client.

        Args:
            base_url: Base URL for API requests.
            rate_limiter: Optional rate limiter instance.
            fingerprint: Optional device fingerprint generator.
            timeout: Request timeout in seconds.
        """
        self.base_url = base_url.rstrip("/")
        self.rate_limiter = rate_limiter or RateLimiter(
            requests_per_second=settings.requests_per_second,
            burst_size=settings.burst_size,
        )
        self.fingerprint = fingerprint
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._auth_token: Optional[str] = None
        self._extra_headers: Dict[str, str] = {}

    async def __aenter__(self) -> "AsyncAPIClient":
        """Enter async context."""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            limits=httpx.Limits(
                max_connections=settings.max_connections,
                max_keepalive_connections=5,
            ),
            http2=True,  # Use HTTP/2 if available
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context."""
        if self._client:
            await self._client.aclose()

    def set_auth_token(self, token: str) -> None:
        """Set the authentication token.

        Args:
            token: Bearer token for authentication.
        """
        self._auth_token = token

    def set_extra_headers(self, headers: Dict[str, str]) -> None:
        """Set additional headers to include in all requests.

        Args:
            headers: Dictionary of headers to add.
        """
        self._extra_headers.update(headers)

    def _build_headers(self, extra_headers: Dict[str, str] = None) -> Dict[str, str]:
        """Build request headers with fingerprint and auth.

        Args:
            extra_headers: Additional headers for this request.

        Returns:
            Complete headers dictionary.
        """
        headers = {}

        # Add fingerprint headers if available
        if self.fingerprint:
            headers.update(self.fingerprint.get_headers())

        # Add persistent extra headers
        headers.update(self._extra_headers)

        # Add auth token
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        # Add request-specific headers
        if extra_headers:
            headers.update(extra_headers)

        return headers

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((NetworkError, httpx.TimeoutException)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def request(
        self,
        method: str,
        endpoint: str,
        params: Dict[str, Any] = None,
        json_data: Dict[str, Any] = None,
        data: Dict[str, Any] = None,
        extra_headers: Dict[str, str] = None,
        add_jitter: bool = True,
    ) -> Dict[str, Any]:
        """Make an HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.).
            endpoint: API endpoint path.
            params: Query parameters.
            json_data: JSON body data.
            data: Form data.
            extra_headers: Additional headers for this request.
            add_jitter: Whether to add random delay before request.

        Returns:
            Parsed JSON response.

        Raises:
            AuthenticationError: If authentication fails.
            RateLimitError: If rate limit is hit.
            APIError: For other API errors.
            NetworkError: For network-level errors.
        """
        # Add jitter for anti-detection
        if add_jitter:
            await RequestJitter.wait_between_requests(
                settings.min_request_delay,
                settings.max_request_delay,
            )

        # Apply rate limiting
        await self.rate_limiter.acquire()

        url = f"{self.base_url}{endpoint}"
        headers = self._build_headers(extra_headers)

        try:
            response = await self._client.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                data=data,
                headers=headers,
            )

            return await self._handle_response(response)

        except httpx.TimeoutException as e:
            logger.warning(f"Request timeout for {url}: {e}")
            raise NetworkError(f"Timeout: {e}")
        except httpx.NetworkError as e:
            logger.warning(f"Network error for {url}: {e}")
            raise NetworkError(f"Network error: {e}")

    async def _handle_response(self, response: httpx.Response) -> Dict[str, Any]:
        """Handle HTTP response and errors.

        Args:
            response: HTTP response object.

        Returns:
            Parsed JSON response.

        Raises:
            AuthenticationError: If authentication fails.
            RateLimitError: If rate limit is hit.
            APIError: For other API errors.
        """
        if response.status_code == 200:
            return response.json()

        elif response.status_code == 401:
            raise AuthenticationError("Authentication failed or token expired")

        elif response.status_code == 403:
            raise AuthenticationError("Access forbidden - possible detection")

        elif response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            logger.warning(f"Rate limited. Waiting {retry_after}s")
            await asyncio.sleep(retry_after)
            raise RateLimitError(retry_after)

        elif response.status_code >= 500:
            raise APIError(
                response.status_code,
                "Server error",
                response.text,
            )

        else:
            raise APIError(
                response.status_code,
                f"Unexpected status code",
                response.text,
            )

    async def get(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make a GET request.

        Args:
            endpoint: API endpoint.
            **kwargs: Additional arguments for request().

        Returns:
            Parsed JSON response.
        """
        return await self.request("GET", endpoint, **kwargs)

    async def post(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make a POST request.

        Args:
            endpoint: API endpoint.
            **kwargs: Additional arguments for request().

        Returns:
            Parsed JSON response.
        """
        return await self.request("POST", endpoint, **kwargs)

    async def put(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make a PUT request.

        Args:
            endpoint: API endpoint.
            **kwargs: Additional arguments for request().

        Returns:
            Parsed JSON response.
        """
        return await self.request("PUT", endpoint, **kwargs)

    async def delete(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make a DELETE request.

        Args:
            endpoint: API endpoint.
            **kwargs: Additional arguments for request().

        Returns:
            Parsed JSON response.
        """
        return await self.request("DELETE", endpoint, **kwargs)
