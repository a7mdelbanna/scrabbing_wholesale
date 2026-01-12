"""Export API routes for data export functionality."""
import os
from typing import Optional, Dict, Any, List
from datetime import datetime

from fastapi import APIRouter, Depends, Query, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.api.middleware.error_handler import NotFoundError, ValidationError
from src.api.schemas.common import PaginatedResponse, PaginationMeta
from src.models.database import ExportJob
from src.services.export_service import ExportService

router = APIRouter(prefix="/export", tags=["Export"])


class ExportJobResponse(BaseModel):
    """Export job response schema."""

    id: int = Field(..., description="Job ID")
    job_type: str = Field(..., description="Export type")
    status: str = Field(..., description="Job status")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Export parameters")
    file_name: Optional[str] = Field(None, description="Output filename")
    file_size_bytes: Optional[int] = Field(None, description="File size")
    records_count: Optional[int] = Field(None, description="Records exported")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    started_at: Optional[datetime] = Field(None, description="Start time")
    completed_at: Optional[datetime] = Field(None, description="Completion time")
    expires_at: Optional[datetime] = Field(None, description="File expiration time")
    created_at: datetime = Field(..., description="Created timestamp")

    class Config:
        from_attributes = True


class ProductsExportRequest(BaseModel):
    """Products export request."""

    source_app: Optional[str] = Field(None, description="Filter by source app")
    category_id: Optional[int] = Field(None, description="Filter by category")
    brand_id: Optional[int] = Field(None, description="Filter by brand")
    include_prices: bool = Field(default=True, description="Include current prices")


class PricesExportRequest(BaseModel):
    """Prices export request."""

    source_app: Optional[str] = Field(None, description="Filter by source app")
    product_id: Optional[int] = Field(None, description="Filter by product")
    start_date: Optional[datetime] = Field(None, description="Start date")
    end_date: Optional[datetime] = Field(None, description="End date")


class ComparisonExportRequest(BaseModel):
    """Comparison export request."""

    apps: Optional[str] = Field(None, description="Comma-separated apps to compare")
    category_id: Optional[int] = Field(None, description="Filter by category")


class ImagesExportRequest(BaseModel):
    """Images export request."""

    source_app: Optional[str] = Field(None, description="Filter by source app")
    category_id: Optional[int] = Field(None, description="Filter by category")
    max_images: int = Field(default=1000, ge=1, le=10000, description="Maximum images")


def build_job_response(job: ExportJob) -> ExportJobResponse:
    """Build export job response from ORM model."""
    return ExportJobResponse(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        parameters=job.parameters,
        file_name=job.file_name,
        file_size_bytes=job.file_size_bytes,
        records_count=job.records_count,
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
        expires_at=job.expires_at,
        created_at=job.created_at,
    )


@router.get("/jobs", response_model=PaginatedResponse[ExportJobResponse])
async def list_export_jobs(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    job_type: Optional[str] = Query(None, description="Filter by job type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
):
    """List export jobs with filters."""
    query = db.query(ExportJob)

    if job_type:
        query = query.filter(ExportJob.job_type == job_type)
    if status:
        query = query.filter(ExportJob.status == status)

    total = query.count()

    offset = (page - 1) * per_page
    jobs = (
        query
        .order_by(ExportJob.created_at.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )

    items = [build_job_response(job) for job in jobs]
    meta = PaginationMeta.from_pagination(total, page, per_page)

    return PaginatedResponse(data=items, meta=meta)


@router.post("/products", response_model=ExportJobResponse)
async def export_products(
    request: ProductsExportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Export products to CSV.

    Creates an export job and processes it synchronously.
    For large exports, this will be processed in the background.
    """
    service = ExportService(db)

    # Create job
    job = service.create_export_job(
        job_type="products_csv",
        parameters=request.model_dump(),
    )

    # Process synchronously for now (can be made async with Celery later)
    job = service.process_products_export(
        job_id=job.id,
        source_app=request.source_app,
        category_id=request.category_id,
        brand_id=request.brand_id,
        include_prices=request.include_prices,
    )

    return build_job_response(job)


@router.post("/prices", response_model=ExportJobResponse)
async def export_prices(
    request: PricesExportRequest,
    db: Session = Depends(get_db),
):
    """Export price history to CSV."""
    service = ExportService(db)

    # Create job
    job = service.create_export_job(
        job_type="prices_csv",
        parameters=request.model_dump(),
    )

    # Process synchronously
    job = service.process_prices_export(
        job_id=job.id,
        source_app=request.source_app,
        product_id=request.product_id,
        start_date=request.start_date,
        end_date=request.end_date,
    )

    return build_job_response(job)


@router.post("/comparison", response_model=ExportJobResponse)
async def export_comparison(
    request: ComparisonExportRequest,
    db: Session = Depends(get_db),
):
    """Export comparison data to CSV."""
    service = ExportService(db)

    # Parse apps
    apps = request.apps.split(",") if request.apps else None

    # Create job
    job = service.create_export_job(
        job_type="comparison_csv",
        parameters=request.model_dump(),
    )

    # Process synchronously
    job = service.process_comparison_export(
        job_id=job.id,
        apps=apps,
        category_id=request.category_id,
    )

    return build_job_response(job)


@router.post("/images")
async def export_images(
    request: ImagesExportRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get image URLs for batch download.

    Returns a list of image URLs with suggested filenames based on barcode/SKU.
    Actual downloading should be done client-side or via a separate batch job.
    """
    service = ExportService(db)

    images = service.get_image_urls_for_export(
        source_app=request.source_app,
        category_id=request.category_id,
        max_images=request.max_images,
    )

    return {
        "total_images": len(images),
        "images": images,
        "note": "Use these URLs to download images. Filenames are based on barcode/SKU.",
    }


@router.get("/jobs/{job_id}", response_model=ExportJobResponse)
async def get_export_job(
    job_id: int,
    db: Session = Depends(get_db),
):
    """Get export job status."""
    service = ExportService(db)
    job = service.get_export_job(job_id)

    if not job:
        raise NotFoundError("ExportJob", job_id)

    return build_job_response(job)


@router.get("/jobs/{job_id}/download")
async def download_export(
    job_id: int,
    db: Session = Depends(get_db),
):
    """Download completed export file."""
    service = ExportService(db)
    job = service.get_export_job(job_id)

    if not job:
        raise NotFoundError("ExportJob", job_id)

    if job.status != "completed":
        raise ValidationError(f"Export job is not completed. Status: {job.status}")

    if not job.file_path or not os.path.exists(job.file_path):
        raise ValidationError("Export file not found or expired")

    return FileResponse(
        path=job.file_path,
        filename=job.file_name or f"export_{job_id}.csv",
        media_type="text/csv",
    )


@router.get("/quick/products")
async def quick_export_products(
    source_app: Optional[str] = Query(None, description="Filter by source app"),
    category_id: Optional[int] = Query(None, description="Filter by category"),
    include_prices: bool = Query(True, description="Include prices"),
    db: Session = Depends(get_db),
):
    """
    Quick export products to CSV (streaming download).

    This is a simpler endpoint for quick exports without creating a job.
    """
    service = ExportService(db)
    csv_content, count = service.export_products_csv(
        source_app=source_app,
        category_id=category_id,
        include_prices=include_prices,
    )

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"products_export_{timestamp}.csv"

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "X-Records-Count": str(count),
        },
    )


@router.get("/quick/comparison")
async def quick_export_comparison(
    apps: Optional[str] = Query(None, description="Comma-separated apps"),
    category_id: Optional[int] = Query(None, description="Filter by category"),
    db: Session = Depends(get_db),
):
    """
    Quick export comparison to CSV (streaming download).
    """
    service = ExportService(db)
    apps_list = apps.split(",") if apps else None

    csv_content, count = service.export_comparison_csv(
        apps=apps_list,
        category_id=category_id,
    )

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"comparison_export_{timestamp}.csv"

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "X-Records-Count": str(count),
        },
    )
