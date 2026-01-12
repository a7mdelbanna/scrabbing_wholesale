"""Scraper management service."""
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models.database import ScrapeJob, ScheduleConfig, Product, Category, Brand


class ScraperService:
    """Service for managing scraper operations and schedules."""

    AVAILABLE_APPS = ["ben_soliman", "tager_elsaada", "el_rabie", "gomla_shoaib"]

    def __init__(self, db: Session):
        self.db = db

    def get_scraper_status(self) -> Dict[str, Any]:
        """Get current status of all scrapers."""
        # Get running jobs
        running_jobs = (
            self.db.query(ScrapeJob)
            .filter(ScrapeJob.status == "running")
            .all()
        )

        # Get last completed job per app
        last_completed = {}
        for app in self.AVAILABLE_APPS:
            job = (
                self.db.query(ScrapeJob)
                .filter(
                    ScrapeJob.source_app == app,
                    ScrapeJob.status == "completed"
                )
                .order_by(ScrapeJob.completed_at.desc())
                .first()
            )
            if job:
                last_completed[app] = {
                    "job_id": job.id,
                    "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                    "products_scraped": job.products_scraped,
                }

        # Get schedule configs
        schedules = self.get_all_schedules()

        return {
            "running_jobs": [
                {
                    "id": j.id,
                    "source_app": j.source_app,
                    "job_type": j.job_type,
                    "started_at": j.started_at.isoformat() if j.started_at else None,
                    "products_scraped": j.products_scraped,
                }
                for j in running_jobs
            ],
            "last_completed": last_completed,
            "schedules": schedules,
            "apps": self.AVAILABLE_APPS,
        }

    def get_all_schedules(self) -> List[Dict[str, Any]]:
        """Get schedule configurations for all apps."""
        schedules = []

        for app in self.AVAILABLE_APPS:
            config = (
                self.db.query(ScheduleConfig)
                .filter(ScheduleConfig.source_app == app)
                .first()
            )

            if config:
                schedules.append({
                    "source_app": config.source_app,
                    "is_enabled": config.is_enabled,
                    "cron_expression": config.cron_expression,
                    "job_type": config.job_type,
                    "last_run_at": config.last_run_at.isoformat() if config.last_run_at else None,
                    "next_run_at": config.next_run_at.isoformat() if config.next_run_at else None,
                    "last_run_status": config.last_run_status,
                    "last_run_products": config.last_run_products,
                })
            else:
                # Return default config
                schedules.append({
                    "source_app": app,
                    "is_enabled": True,
                    "cron_expression": "0 * * * *",
                    "job_type": "full",
                    "last_run_at": None,
                    "next_run_at": None,
                    "last_run_status": None,
                    "last_run_products": 0,
                })

        return schedules

    def get_schedule(self, source_app: str) -> Optional[Dict[str, Any]]:
        """Get schedule configuration for a specific app."""
        if source_app not in self.AVAILABLE_APPS:
            return None

        config = (
            self.db.query(ScheduleConfig)
            .filter(ScheduleConfig.source_app == source_app)
            .first()
        )

        if config:
            return {
                "source_app": config.source_app,
                "is_enabled": config.is_enabled,
                "cron_expression": config.cron_expression,
                "job_type": config.job_type,
                "max_concurrent_requests": config.max_concurrent_requests,
                "request_delay_ms": config.request_delay_ms,
                "last_run_at": config.last_run_at.isoformat() if config.last_run_at else None,
                "next_run_at": config.next_run_at.isoformat() if config.next_run_at else None,
                "last_run_status": config.last_run_status,
                "last_run_products": config.last_run_products,
            }

        # Return default
        return {
            "source_app": source_app,
            "is_enabled": True,
            "cron_expression": "0 * * * *",
            "job_type": "full",
            "max_concurrent_requests": 3,
            "request_delay_ms": 1000,
            "last_run_at": None,
            "next_run_at": None,
            "last_run_status": None,
            "last_run_products": 0,
        }

    def update_schedule(
        self,
        source_app: str,
        is_enabled: Optional[bool] = None,
        cron_expression: Optional[str] = None,
        job_type: Optional[str] = None,
        max_concurrent_requests: Optional[int] = None,
        request_delay_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Update schedule configuration for an app."""
        if source_app not in self.AVAILABLE_APPS:
            raise ValueError(f"Unknown app: {source_app}")

        config = (
            self.db.query(ScheduleConfig)
            .filter(ScheduleConfig.source_app == source_app)
            .first()
        )

        if not config:
            # Create new config
            config = ScheduleConfig(source_app=source_app)
            self.db.add(config)

        # Update provided fields
        if is_enabled is not None:
            config.is_enabled = is_enabled
        if cron_expression is not None:
            config.cron_expression = cron_expression
        if job_type is not None:
            config.job_type = job_type
        if max_concurrent_requests is not None:
            config.max_concurrent_requests = max_concurrent_requests
        if request_delay_ms is not None:
            config.request_delay_ms = request_delay_ms

        self.db.commit()
        self.db.refresh(config)

        return self.get_schedule(source_app)

    def trigger_scrape(
        self,
        source_app: str,
        job_type: str = "full",
    ) -> ScrapeJob:
        """
        Trigger a manual scrape job.

        Note: This creates the job record. Actual scraping should be handled
        by a background worker (Celery or similar).
        """
        if source_app not in self.AVAILABLE_APPS:
            raise ValueError(f"Unknown app: {source_app}")

        # Check if there's already a running job for this app
        running = (
            self.db.query(ScrapeJob)
            .filter(
                ScrapeJob.source_app == source_app,
                ScrapeJob.status.in_(["pending", "running"])
            )
            .first()
        )

        if running:
            raise ValueError(f"A job is already running for {source_app}")

        # Create new job
        job = ScrapeJob(
            source_app=source_app,
            job_type=job_type,
            status="pending",
            created_at=datetime.utcnow(),
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        return job

    def cancel_job(self, job_id: int) -> ScrapeJob:
        """Cancel a running or pending scrape job."""
        job = self.db.query(ScrapeJob).filter(ScrapeJob.id == job_id).first()
        if not job:
            raise ValueError("Job not found")

        if job.status not in ["pending", "running"]:
            raise ValueError(f"Cannot cancel job in {job.status} status")

        job.status = "cancelled"
        job.completed_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(job)

        return job

    def get_job(self, job_id: int) -> Optional[ScrapeJob]:
        """Get a specific scrape job."""
        return self.db.query(ScrapeJob).filter(ScrapeJob.id == job_id).first()

    def get_jobs(
        self,
        source_app: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[ScrapeJob], int]:
        """Get scrape jobs with filters."""
        query = self.db.query(ScrapeJob)

        if source_app:
            query = query.filter(ScrapeJob.source_app == source_app)
        if status:
            query = query.filter(ScrapeJob.status == status)

        total = query.count()
        jobs = (
            query
            .order_by(ScrapeJob.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return jobs, total

    def get_job_stats(self) -> Dict[str, Any]:
        """Get scrape job statistics."""
        # Total jobs by status
        status_counts = dict(
            self.db.query(ScrapeJob.status, func.count(ScrapeJob.id))
            .group_by(ScrapeJob.status)
            .all()
        )

        # Jobs per app
        app_counts = dict(
            self.db.query(ScrapeJob.source_app, func.count(ScrapeJob.id))
            .group_by(ScrapeJob.source_app)
            .all()
        )

        # Average products per successful job
        avg_products = (
            self.db.query(func.avg(ScrapeJob.products_scraped))
            .filter(ScrapeJob.status == "completed")
            .scalar()
        )

        # Jobs in last 24 hours
        yesterday = datetime.utcnow() - timedelta(hours=24)
        recent_jobs = (
            self.db.query(func.count(ScrapeJob.id))
            .filter(ScrapeJob.created_at >= yesterday)
            .scalar()
        )

        # Total products scraped (sum of all completed jobs)
        total_products = (
            self.db.query(func.sum(ScrapeJob.products_scraped))
            .filter(ScrapeJob.status == "completed")
            .scalar()
        ) or 0

        return {
            "total_jobs": sum(status_counts.values()),
            "by_status": status_counts,
            "by_app": app_counts,
            "avg_products_per_job": round(float(avg_products), 2) if avg_products else 0,
            "jobs_last_24h": recent_jobs,
            "total_products_scraped": total_products,
        }

    def update_job_progress(
        self,
        job_id: int,
        products_scraped: int,
        products_updated: int = 0,
        products_new: int = 0,
        errors_count: int = 0,
        status: Optional[str] = None,
    ) -> Optional[ScrapeJob]:
        """Update job progress (called by scraper)."""
        job = self.db.query(ScrapeJob).filter(ScrapeJob.id == job_id).first()
        if not job:
            return None

        job.products_scraped = products_scraped
        job.products_updated = products_updated
        job.products_new = products_new
        job.errors_count = errors_count

        if status:
            job.status = status
            if status == "running" and not job.started_at:
                job.started_at = datetime.utcnow()
            elif status in ["completed", "failed", "cancelled"]:
                job.completed_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(job)

        return job
