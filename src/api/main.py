"""Main FastAPI application for the backend API.

This is the entry point for the backend microservice API.
Run with: uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.database.connection import init_db
from src.api.routes import (
    products,
    categories,
    brands,
    comparison,
    product_links,
    offers,
    banners,
    scraper,
    export,
    images,
    analytics,
    auth,
    system,
)
from src.api.middleware.error_handler import APIException
from src.api.middleware.rate_limiter import rate_limit_middleware
from src.api.middleware.request_logger import request_logging_middleware

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup
    logger.info("Starting API server...")
    await init_db()
    logger.info("Database initialized")

    yield

    # Shutdown
    logger.info("Shutting down API server...")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Competitor Price Scraping API",
        description="""
Backend microservice API for competitor price scraping system.

## Features
- **Products**: Full CRUD operations with filtering, search, and pagination
- **Categories**: Hierarchical category management
- **Brands**: Brand catalog management
- **Comparison**: Cross-app price comparison with advanced filtering
- **Product Linking**: Auto and manual product linking across apps
- **Offers**: Track promotional offers and discounts
- **Banners**: Promotional banner management
- **Scraper**: Trigger, schedule, and monitor scraping jobs
- **Export**: Export data to CSV/Excel/ZIP
- **Analytics**: Price trends, availability, and performance metrics

## Authentication
All endpoints (except /health) require API key authentication.
Include your API key in the `X-API-Key` header.
        """,
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limiting middleware
    app.add_middleware(BaseHTTPMiddleware, dispatch=rate_limit_middleware)

    # Request logging middleware
    app.add_middleware(BaseHTTPMiddleware, dispatch=request_logging_middleware)

    # Exception handler for custom API exceptions
    @app.exception_handler(APIException)
    async def api_exception_handler(request: Request, exc: APIException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.error_code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    # Global exception handler for unhandled errors
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred",
                    "details": {"type": type(exc).__name__} if logger.isEnabledFor(logging.DEBUG) else {},
                }
            },
        )

    # Include routers with /api/v1 prefix
    # Note: Routers already have their own prefix (e.g., /system, /products)
    # so we only add /api/v1 here
    api_v1_prefix = "/api/v1"

    app.include_router(system.router, prefix=api_v1_prefix)
    app.include_router(auth.router, prefix=api_v1_prefix)
    app.include_router(products.router, prefix=api_v1_prefix)
    app.include_router(categories.router, prefix=api_v1_prefix)
    app.include_router(brands.router, prefix=api_v1_prefix)
    app.include_router(comparison.router, prefix=api_v1_prefix)
    app.include_router(product_links.router, prefix=api_v1_prefix)
    app.include_router(offers.router, prefix=api_v1_prefix)
    app.include_router(banners.router, prefix=api_v1_prefix)
    app.include_router(scraper.router, prefix=api_v1_prefix)
    app.include_router(export.router, prefix=api_v1_prefix)
    app.include_router(images.router, prefix=api_v1_prefix)
    app.include_router(analytics.router, prefix=api_v1_prefix)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
