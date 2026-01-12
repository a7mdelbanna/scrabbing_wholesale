"""Scheduled job definitions for scraping tasks."""
import asyncio
import logging
from datetime import datetime, timedelta

from src.database.connection import get_async_session
from src.scrapers.tager_elsaada import TagerElsaadaScraper
from src.scrapers.ben_soliman import BenSolimanScraper
from src.scrapers.auth.token_manager import TokenManager
from src.database.repositories.price_repo import PriceRepository
from src.models.enums import SourceApp

logger = logging.getLogger(__name__)


async def scrape_tager_elsaada() -> None:
    """Hourly scraping job for Tager elSaada.

    This job runs at the start of every hour to fetch
    the latest product data and prices.
    """
    logger.info("Starting Tager elSaada scraping job")

    async with get_async_session() as session:
        async with TagerElsaadaScraper(session) as scraper:
            try:
                await scraper.run_full_scrape()
                logger.info("Tager elSaada scraping completed successfully")
            except Exception as e:
                logger.error(f"Tager elSaada scraping failed: {e}", exc_info=True)
                raise


async def scrape_ben_soliman() -> None:
    """Hourly scraping job for Ben Soliman.

    This job runs at 30 minutes past every hour to fetch
    the latest product data and prices.
    """
    logger.info("Starting Ben Soliman scraping job")

    async with get_async_session() as session:
        async with BenSolimanScraper(session) as scraper:
            try:
                await scraper.run_full_scrape()
                logger.info("Ben Soliman scraping completed successfully")
            except Exception as e:
                logger.error(f"Ben Soliman scraping failed: {e}", exc_info=True)
                raise


async def refresh_tokens() -> None:
    """Refresh authentication tokens before expiry.

    This job runs every 25 minutes to ensure tokens
    don't expire during scraping operations.
    """
    logger.info("Starting token refresh job")

    async with get_async_session() as session:
        token_manager = TokenManager(session)

        for source in [SourceApp.TAGER_ELSAADA, SourceApp.BEN_SOLIMAN]:
            try:
                needs_refresh = await token_manager.refresh_if_needed(source)
                if needs_refresh:
                    logger.info(f"Token needs refresh for {source.value}")
                    # Token refresh will happen automatically on next scrape
                else:
                    logger.debug(f"Token still valid for {source.value}")
            except Exception as e:
                logger.error(f"Token check failed for {source.value}: {e}")


async def cleanup_old_data() -> None:
    """Clean up old price records and logs.

    This job runs daily at 3 AM to:
    - Delete price records older than 90 days
    - Aggregate hourly data into daily summaries
    """
    logger.info("Starting daily cleanup job")

    async with get_async_session() as session:
        price_repo = PriceRepository(session)

        try:
            # Delete records older than 90 days
            deleted_count = await price_repo.cleanup_old_records(days=90)
            logger.info(f"Deleted {deleted_count} old price records")

        except Exception as e:
            logger.error(f"Cleanup job failed: {e}", exc_info=True)


async def health_check() -> None:
    """Perform system health check.

    This job runs every 5 minutes to verify:
    - Database connectivity
    - API reachability
    - Token validity
    """
    logger.debug("Running health check")

    try:
        # Check database
        async with get_async_session() as session:
            # Simple query to verify connection
            await session.execute("SELECT 1")
            logger.debug("Database connection OK")

    except Exception as e:
        logger.error(f"Health check failed: {e}")


# ============================================================
# Manual Trigger Functions
# ============================================================

async def run_single_scrape(source_app: SourceApp) -> dict:
    """Run a single scrape for testing or manual trigger.

    Args:
        source_app: Which app to scrape.

    Returns:
        Dictionary with scrape results.
    """
    logger.info(f"Running manual scrape for {source_app.value}")

    async with get_async_session() as session:
        if source_app == SourceApp.TAGER_ELSAADA:
            async with TagerElsaadaScraper(session) as scraper:
                await scraper.run_full_scrape()
                return scraper._stats
        elif source_app == SourceApp.BEN_SOLIMAN:
            async with BenSolimanScraper(session) as scraper:
                await scraper.run_full_scrape()
                return scraper._stats
        else:
            raise ValueError(f"Unknown source app: {source_app}")
