"""Main entry point for the competitor scraper application."""
import asyncio
import signal
import logging
import sys
from typing import Optional

import structlog

from src.config.settings import settings
from src.database.connection import init_db, close_db
from src.scheduler.scheduler import create_scheduler, register_jobs

# Global scheduler instance
scheduler: Optional[asyncio.AbstractEventLoop] = None
shutdown_event: Optional[asyncio.Event] = None


def setup_logging() -> None:
    """Configure structured logging."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if settings.environment == "production"
            else structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Set log level
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper()),
    )


def handle_shutdown(sig, frame) -> None:
    """Handle shutdown signals gracefully."""
    logger = structlog.get_logger()
    logger.info(f"Received signal {sig}, initiating shutdown...")

    if shutdown_event:
        shutdown_event.set()


async def main() -> None:
    """Main application entry point."""
    global scheduler, shutdown_event

    # Setup logging
    setup_logging()
    logger = structlog.get_logger()

    logger.info("=" * 60)
    logger.info("Competitor Product Scraper")
    logger.info("=" * 60)
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Log Level: {settings.log_level}")
    logger.info(f"Timezone: {settings.timezone}")
    logger.info("=" * 60)

    # Create shutdown event
    shutdown_event = asyncio.Event()

    # Register signal handlers
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    try:
        # Initialize database
        logger.info("Initializing database...")
        await init_db()
        logger.info("Database initialized successfully")

        # Create and configure scheduler
        logger.info("Setting up scheduler...")
        scheduler = create_scheduler()
        register_jobs(scheduler)

        # Start scheduler
        scheduler.start()
        logger.info("Scheduler started - jobs are now running")

        # Print next run times
        logger.info("Scheduled jobs:")
        for job in scheduler.get_jobs():
            next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if job.next_run_time else "N/A"
            logger.info(f"  {job.name}: next run at {next_run}")

        # Wait for shutdown signal
        logger.info("Application running. Press Ctrl+C to stop.")
        await shutdown_event.wait()

    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
        raise

    finally:
        # Cleanup
        logger.info("Shutting down...")

        if scheduler:
            scheduler.shutdown(wait=True)
            logger.info("Scheduler stopped")

        await close_db()
        logger.info("Database connections closed")

        logger.info("Shutdown complete")


def run() -> None:
    """Entry point for running the application."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
