"""Scraper management API routes."""
from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.api.middleware.error_handler import NotFoundError
from src.api.schemas.common import PaginatedResponse, PaginationMeta, SuccessResponse
from src.models.database import ScrapeJob

router = APIRouter(prefix="/scraper", tags=["Scraper Management"])


class ScrapeJobResponse(BaseModel):
    """Scrape job response schema."""

    id: int = Field(..., description="Job ID")
    source_app: str = Field(..., description="Source application")
    job_type: str = Field(..., description="Job type")
    status: str = Field(..., description="Job status")
    started_at: Optional[datetime] = Field(None, description="Start time")
    completed_at: Optional[datetime] = Field(None, description="Completion time")
    products_scraped: int = Field(default=0, description="Products scraped")
    products_updated: int = Field(default=0, description="Products updated")
    products_new: int = Field(default=0, description="New products")
    errors_count: int = Field(default=0, description="Error count")
    error_details: Optional[Dict[str, Any]] = Field(None, description="Error details")
    created_at: datetime = Field(..., description="Created timestamp")

    class Config:
        from_attributes = True


class ScheduleConfigResponse(BaseModel):
    """Schedule configuration response."""

    source_app: str
    is_enabled: bool = True
    cron_expression: Optional[str] = None
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None


class ScheduleConfigUpdate(BaseModel):
    """Schedule configuration update request."""

    is_enabled: Optional[bool] = None
    cron_expression: Optional[str] = None


class TriggerScrapeRequest(BaseModel):
    """Trigger scrape request."""

    source_app: str = Field(..., description="Source app to scrape")
    job_type: str = Field(default="full", description="Job type (full, incremental, categories)")


@router.get("/jobs", response_model=PaginatedResponse[ScrapeJobResponse])
async def list_scrape_jobs(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    source_app: Optional[str] = Query(None, description="Filter by source app"),
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
):
    """List scrape jobs with filters."""
    query = db.query(ScrapeJob)

    if source_app:
        query = query.filter(ScrapeJob.source_app == source_app)
    if status:
        query = query.filter(ScrapeJob.status == status)

    total = query.count()

    offset = (page - 1) * per_page
    jobs = (
        query
        .order_by(ScrapeJob.created_at.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )

    items = [
        ScrapeJobResponse(
            id=j.id,
            source_app=j.source_app,
            job_type=j.job_type,
            status=j.status,
            started_at=j.started_at,
            completed_at=j.completed_at,
            products_scraped=j.products_scraped,
            products_updated=j.products_updated,
            products_new=j.products_new,
            errors_count=j.errors_count,
            error_details=j.error_details,
            created_at=j.created_at,
        )
        for j in jobs
    ]

    meta = PaginationMeta.from_pagination(total, page, per_page)
    return PaginatedResponse(data=items, meta=meta)


@router.get("/jobs/{job_id}", response_model=ScrapeJobResponse)
async def get_scrape_job(
    job_id: int,
    db: Session = Depends(get_db),
):
    """Get scrape job details by ID."""
    job = db.query(ScrapeJob).filter(ScrapeJob.id == job_id).first()
    if not job:
        raise NotFoundError("ScrapeJob", job_id)

    return ScrapeJobResponse(
        id=job.id,
        source_app=job.source_app,
        job_type=job.job_type,
        status=job.status,
        started_at=job.started_at,
        completed_at=job.completed_at,
        products_scraped=job.products_scraped,
        products_updated=job.products_updated,
        products_new=job.products_new,
        errors_count=job.errors_count,
        error_details=job.error_details,
        created_at=job.created_at,
    )


@router.post("/jobs/{job_id}/cancel")
async def cancel_scrape_job(
    job_id: int,
    db: Session = Depends(get_db),
) -> SuccessResponse:
    """Cancel a running scrape job."""
    job = db.query(ScrapeJob).filter(ScrapeJob.id == job_id).first()
    if not job:
        raise NotFoundError("ScrapeJob", job_id)

    if job.status != "running":
        from src.api.middleware.error_handler import ValidationError
        raise ValidationError("Can only cancel running jobs")

    job.status = "cancelled"
    job.completed_at = datetime.utcnow()
    db.commit()

    return SuccessResponse(message=f"Job {job_id} cancelled")


@router.post("/trigger")
async def trigger_scrape(
    request: TriggerScrapeRequest,
    db: Session = Depends(get_db),
) -> ScrapeJobResponse:
    """Trigger a manual scrape job."""
    # Create a new scrape job
    job = ScrapeJob(
        source_app=request.source_app,
        job_type=request.job_type,
        status="pending",
        created_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # TODO: In Phase 3, trigger actual scraper via Celery
    # For now, just return the created job

    return ScrapeJobResponse(
        id=job.id,
        source_app=job.source_app,
        job_type=job.job_type,
        status=job.status,
        started_at=job.started_at,
        completed_at=job.completed_at,
        products_scraped=job.products_scraped,
        products_updated=job.products_updated,
        products_new=job.products_new,
        errors_count=job.errors_count,
        error_details=job.error_details,
        created_at=job.created_at,
    )


@router.get("/schedules")
async def get_schedules(
    db: Session = Depends(get_db),
) -> List[ScheduleConfigResponse]:
    """Get scraper schedules for all apps."""
    # TODO: Implement when ScheduleConfig model is added in Phase 3
    # For now, return default schedules
    apps = ["ben_soliman", "tager_elsaada", "el_rabie", "gomla_shoaib"]
    return [
        ScheduleConfigResponse(
            source_app=app,
            is_enabled=True,
            cron_expression="0 * * * *",  # Every hour
            last_run_at=None,
            next_run_at=None,
        )
        for app in apps
    ]


@router.put("/schedules/{source_app}")
async def update_schedule(
    source_app: str,
    config: ScheduleConfigUpdate,
    db: Session = Depends(get_db),
) -> ScheduleConfigResponse:
    """Update scraper schedule for an app."""
    # TODO: Implement when ScheduleConfig model is added in Phase 3
    return ScheduleConfigResponse(
        source_app=source_app,
        is_enabled=config.is_enabled if config.is_enabled is not None else True,
        cron_expression=config.cron_expression or "0 * * * *",
    )


@router.get("/status")
async def get_scraper_status(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get current scraper status across all apps."""
    # Get running jobs
    running_jobs = (
        db.query(ScrapeJob)
        .filter(ScrapeJob.status == "running")
        .all()
    )

    # Get last completed job per app
    from sqlalchemy import func
    last_jobs = (
        db.query(ScrapeJob.source_app, func.max(ScrapeJob.completed_at))
        .filter(ScrapeJob.status == "completed")
        .group_by(ScrapeJob.source_app)
        .all()
    )

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
        "last_completed": {
            app: time.isoformat() if time else None
            for app, time in last_jobs
        },
        "apps": ["ben_soliman", "tager_elsaada", "el_rabie", "gomla_shoaib"],
    }
