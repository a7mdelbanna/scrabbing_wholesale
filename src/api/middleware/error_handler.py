"""Error handling middleware and custom exceptions."""
from typing import Any, Dict, Optional


class APIException(Exception):
    """Base exception for API errors."""

    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class NotFoundError(APIException):
    """Resource not found error."""

    def __init__(self, resource: str, identifier: Any):
        super().__init__(
            status_code=404,
            error_code="NOT_FOUND",
            message=f"{resource} not found",
            details={"resource": resource, "identifier": str(identifier)},
        )


class ValidationError(APIException):
    """Validation error."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=400,
            error_code="VALIDATION_ERROR",
            message=message,
            details=details,
        )


class AuthenticationError(APIException):
    """Authentication error."""

    def __init__(self, message: str = "Invalid or missing API key"):
        super().__init__(
            status_code=401,
            error_code="AUTHENTICATION_ERROR",
            message=message,
        )


class AuthorizationError(APIException):
    """Authorization error."""

    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(
            status_code=403,
            error_code="AUTHORIZATION_ERROR",
            message=message,
        )


class RateLimitError(APIException):
    """Rate limit exceeded error."""

    def __init__(self, retry_after: int = 60):
        super().__init__(
            status_code=429,
            error_code="RATE_LIMIT_EXCEEDED",
            message="Rate limit exceeded. Please try again later.",
            details={"retry_after_seconds": retry_after},
        )


class ConflictError(APIException):
    """Resource conflict error."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=409,
            error_code="CONFLICT",
            message=message,
            details=details,
        )


class InternalError(APIException):
    """Internal server error."""

    def __init__(self, message: str = "An internal error occurred"):
        super().__init__(
            status_code=500,
            error_code="INTERNAL_ERROR",
            message=message,
        )
