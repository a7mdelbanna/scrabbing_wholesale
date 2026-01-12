"""Custom exceptions for the scraper."""


class ScraperException(Exception):
    """Base exception for scraper errors."""
    pass


class AuthenticationError(ScraperException):
    """Raised when authentication fails."""
    pass


class TokenExpiredError(AuthenticationError):
    """Raised when access token has expired."""
    pass


class RateLimitError(ScraperException):
    """Raised when rate limit is hit."""

    def __init__(self, retry_after: int = None, message: str = None):
        self.retry_after = retry_after
        msg = message or f"Rate limited. Retry after {retry_after}s"
        super().__init__(msg)


class APIError(ScraperException):
    """Raised for API-level errors."""

    def __init__(self, status_code: int, message: str, response_body: str = None):
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(f"API Error {status_code}: {message}")


class DataValidationError(ScraperException):
    """Raised when API response doesn't match expected schema."""
    pass


class NetworkError(ScraperException):
    """Raised for network-level errors."""
    pass
