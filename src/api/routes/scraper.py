"""Scraper management API routes."""
from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.api.middleware.error_handler import NotFoundError, ValidationError
from src.api.schemas.common import PaginatedResponse, PaginationMeta, SuccessResponse
from src.models.database import ScrapeJob
from src.services.scraper_service import ScraperService

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
    cron_expression: str = "0 * * * *"
    job_type: str = "full"
    max_concurrent_requests: Optional[int] = 3
    request_delay_ms: Optional[int] = 1000
    last_run_at: Optional[str] = None
    next_run_at: Optional[str] = None
    last_run_status: Optional[str] = None
    last_run_products: int = 0


class ScheduleConfigUpdate(BaseModel):
    """Schedule configuration update request."""

    is_enabled: Optional[bool] = None
    cron_expression: Optional[str] = None
    job_type: Optional[str] = None
    max_concurrent_requests: Optional[int] = Field(None, ge=1, le=10)
    request_delay_ms: Optional[int] = Field(None, ge=100, le=10000)


class TriggerScrapeRequest(BaseModel):
    """Trigger scrape request."""

    source_app: str = Field(..., description="Source app to scrape")
    job_type: str = Field(default="full", description="Job type (full, incremental, categories)")


def build_job_response(job: ScrapeJob) -> ScrapeJobResponse:
    """Build job response from ORM model."""
    return ScrapeJobResponse(
        id=job.id,
        source_app=job.source_app,
        job_type=job.job_type,
        status=job.status,
        started_at=job.started_at,
        completed_at=job.completed_at,
        products_scraped=job.products_scraped or 0,
        products_updated=job.products_updated or 0,
        products_new=job.products_new or 0,
        errors_count=job.errors_count or 0,
        error_details=job.error_details,
        created_at=job.created_at,
    )


@router.get("/status")
async def get_scraper_status(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get current scraper status across all apps."""
    service = ScraperService(db)
    return service.get_scraper_status()


@router.get("/stats")
async def get_scraper_stats(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get scraper job statistics."""
    service = ScraperService(db)
    return service.get_job_stats()


@router.get("/jobs", response_model=PaginatedResponse[ScrapeJobResponse])
async def list_scrape_jobs(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    source_app: Optional[str] = Query(None, description="Filter by source app"),
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
):
    """List scrape jobs with filters."""
    service = ScraperService(db)
    offset = (page - 1) * per_page
    jobs, total = service.get_jobs(
        source_app=source_app,
        status=status,
        limit=per_page,
        offset=offset,
    )

    items = [build_job_response(job) for job in jobs]
    meta = PaginationMeta.from_pagination(total, page, per_page)

    return PaginatedResponse(data=items, meta=meta)


@router.get("/jobs/{job_id}", response_model=ScrapeJobResponse)
async def get_scrape_job(
    job_id: int,
    db: Session = Depends(get_db),
):
    """Get scrape job details by ID."""
    service = ScraperService(db)
    job = service.get_job(job_id)

    if not job:
        raise NotFoundError("ScrapeJob", job_id)

    return build_job_response(job)


@router.post("/jobs/{job_id}/cancel")
async def cancel_scrape_job(
    job_id: int,
    db: Session = Depends(get_db),
) -> SuccessResponse:
    """Cancel a running or pending scrape job."""
    service = ScraperService(db)

    try:
        job = service.cancel_job(job_id)
        return SuccessResponse(message=f"Job {job_id} cancelled successfully")
    except ValueError as e:
        if "not found" in str(e).lower():
            raise NotFoundError("ScrapeJob", job_id)
        raise ValidationError(str(e))


@router.post("/trigger", response_model=ScrapeJobResponse)
async def trigger_scrape(
    request: TriggerScrapeRequest,
    db: Session = Depends(get_db),
):
    """
    Trigger a manual scrape job.

    This creates a pending job that will be picked up by the scraper worker.
    """
    service = ScraperService(db)

    try:
        job = service.trigger_scrape(
            source_app=request.source_app,
            job_type=request.job_type,
        )
        return build_job_response(job)
    except ValueError as e:
        raise ValidationError(str(e))


@router.get("/schedules", response_model=List[ScheduleConfigResponse])
async def get_schedules(
    db: Session = Depends(get_db),
):
    """Get scraper schedules for all apps."""
    service = ScraperService(db)
    schedules = service.get_all_schedules()
    return [ScheduleConfigResponse(**s) for s in schedules]


@router.get("/schedules/{source_app}", response_model=ScheduleConfigResponse)
async def get_schedule(
    source_app: str,
    db: Session = Depends(get_db),
):
    """Get schedule configuration for a specific app."""
    service = ScraperService(db)
    schedule = service.get_schedule(source_app)

    if not schedule:
        raise NotFoundError("Schedule", source_app)

    return ScheduleConfigResponse(**schedule)


@router.put("/schedules/{source_app}", response_model=ScheduleConfigResponse)
async def update_schedule(
    source_app: str,
    config: ScheduleConfigUpdate,
    db: Session = Depends(get_db),
):
    """Update scraper schedule for an app."""
    service = ScraperService(db)

    try:
        updated = service.update_schedule(
            source_app=source_app,
            is_enabled=config.is_enabled,
            cron_expression=config.cron_expression,
            job_type=config.job_type,
            max_concurrent_requests=config.max_concurrent_requests,
            request_delay_ms=config.request_delay_ms,
        )
        return ScheduleConfigResponse(**updated)
    except ValueError as e:
        raise ValidationError(str(e))


@router.get("/apps")
async def get_available_apps(
    db: Session = Depends(get_db),
) -> List[str]:
    """Get list of available scraper apps."""
    return ScraperService.AVAILABLE_APPS
