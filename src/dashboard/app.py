"""FastAPI dashboard application."""
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse

from src.database.connection import init_db, close_db

logger = logging.getLogger(__name__)

# Template directory
TEMPLATE_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
# Project-level static dir for downloaded images
PROJECT_STATIC_DIR = Path(__file__).parent.parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting dashboard application...")
    try:
        await init_db()
        logger.info("Database connected successfully")
    except Exception as e:
        logger.warning(f"Database connection failed: {e}. Dashboard will run without database.")
    yield
    # Shutdown
    logger.info("Shutting down dashboard application...")
    try:
        await close_db()
    except Exception:
        pass


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Competitor Price Dashboard",
        description="Dashboard for viewing scraped competitor product data",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Setup templates
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    app.state.templates = templates

    # Register routes FIRST
    from src.dashboard.routes.pages import router as pages_router
    from src.dashboard.routes.api import router as api_router

    app.include_router(pages_router)
    app.include_router(api_router, prefix="/api")

    # Mount static files AFTER routes - project level (for downloaded images)
    if PROJECT_STATIC_DIR.exists():
        logger.info(f"Mounting static files from: {PROJECT_STATIC_DIR.resolve()}")
        app.mount("/static", StaticFiles(directory=str(PROJECT_STATIC_DIR.resolve())), name="static")
    # Mount dashboard-specific static files
    elif STATIC_DIR.exists():
        app.mount("/dashboard-static", StaticFiles(directory=str(STATIC_DIR.resolve())), name="dashboard-static")

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy"}

    return app


# Create app instance
app = create_app()
