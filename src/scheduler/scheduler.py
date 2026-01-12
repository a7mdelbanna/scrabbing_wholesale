"""APScheduler configuration for scheduled scraping jobs."""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

from src.config.settings import settings

logger = logging.getLogger(__name__)


def job_listener(event):
    """Listen for job execution events."""
    if event.exception:
        logger.error(f"Job {event.job_id} failed with exception: {event.exception}")
    else:
        logger.info(f"Job {event.job_id} completed successfully")


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler instance.

    Returns:
        Configured AsyncIOScheduler.
    """
    scheduler = AsyncIOScheduler(
        timezone=settings.timezone,
        job_defaults={
            "coalesce": True,  # Combine missed runs into one
            "max_instances": 1,  # Only one instance per job
            "misfire_grace_time": 300,  # 5 minutes grace period
        },
    )

    # Add event listeners
    scheduler.add_listener(job_listener, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED)

    return scheduler


def register_jobs(scheduler: AsyncIOScheduler) -> None:
    """Register all scheduled jobs.

    Args:
        scheduler: The scheduler instance.
    """
    from src.scheduler.jobs import (
        scrape_tager_elsaada,
        scrape_ben_soliman,
        refresh_tokens,
        cleanup_old_data,
        health_check,
    )

    # ============================================================
    # SCRAPING JOBS - Hourly, staggered to avoid concurrent load
    # ============================================================

    # Tager elSaada - At the start of every hour
    scheduler.add_job(
        scrape_tager_elsaada,
        trigger=CronTrigger(minute=0),
        id="scrape_tager_elsaada_hourly",
        name="Scrape Tager elSaada - Hourly",
        replace_existing=True,
    )

    # Ben Soliman - At 30 minutes past every hour
    scheduler.add_job(
        scrape_ben_soliman,
        trigger=CronTrigger(minute=30),
        id="scrape_ben_soliman_hourly",
        name="Scrape Ben Soliman - Hourly",
        replace_existing=True,
    )

    # ============================================================
    # TOKEN MANAGEMENT - Every 25 minutes
    # ============================================================

    scheduler.add_job(
        refresh_tokens,
        trigger=IntervalTrigger(minutes=25),
        id="refresh_tokens",
        name="Refresh Authentication Tokens",
        replace_existing=True,
    )

    # ============================================================
    # MAINTENANCE JOBS
    # ============================================================

    # Daily cleanup at 3 AM Cairo time
    scheduler.add_job(
        cleanup_old_data,
        trigger=CronTrigger(hour=3, minute=0),
        id="cleanup_old_data_daily",
        name="Cleanup Old Data - Daily",
        replace_existing=True,
    )

    # Health check every 5 minutes
    scheduler.add_job(
        health_check,
        trigger=IntervalTrigger(minutes=5),
        id="health_check",
        name="System Health Check",
        replace_existing=True,
    )

    logger.info("All scheduled jobs registered successfully")

    # Log registered jobs
    for job in scheduler.get_jobs():
        logger.info(f"  - {job.id}: {job.name} ({job.trigger})")
