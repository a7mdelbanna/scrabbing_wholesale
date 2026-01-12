"""Request logging middleware for monitoring and debugging."""
import time
import logging
from typing import Callable
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all incoming requests and their responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate request ID
        request_id = str(uuid4())[:8]

        # Start timer
        start_time = time.time()

        # Get request info
        method = request.method
        path = request.url.path
        query = str(request.url.query) if request.url.query else ""
        client_ip = request.client.host if request.client else "unknown"

        # Add request ID to state for tracing
        request.state.request_id = request_id

        # Log incoming request
        logger.info(
            f"[{request_id}] --> {method} {path}"
            + (f"?{query}" if query else "")
            + f" from {client_ip}"
        )

        # Process request
        try:
            response = await call_next(request)

            # Calculate duration
            duration = time.time() - start_time
            duration_ms = round(duration * 1000, 2)

            # Log response
            status_code = response.status_code
            log_level = logging.INFO if status_code < 400 else logging.WARNING

            logger.log(
                log_level,
                f"[{request_id}] <-- {status_code} in {duration_ms}ms"
            )

            # Add request ID to response headers for tracing
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{duration_ms}ms"

            return response

        except Exception as e:
            duration = time.time() - start_time
            duration_ms = round(duration * 1000, 2)

            logger.error(
                f"[{request_id}] <-- ERROR in {duration_ms}ms: {str(e)}"
            )
            raise


async def request_logging_middleware(request: Request, call_next: Callable) -> Response:
    """Functional middleware for request logging."""
    middleware = RequestLoggingMiddleware(app=None)
    return await middleware.dispatch(request, call_next)
