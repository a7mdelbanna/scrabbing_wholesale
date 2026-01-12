"""System routes for health check and statistics."""
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.api.schemas.common import HealthResponse, SuccessResponse
from src.models.database import Product, Category, Brand, PriceRecord, ScrapeJob

router = APIRouter(prefix="/system", tags=["System"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        version="1.0.0",
    )


@router.get("/stats")
async def get_system_stats(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Get system statistics including product counts by source app."""
    # Get product counts by source app
    product_counts = (
        db.query(Product.source_app, func.count(Product.id))
        .group_by(Product.source_app)
        .all()
    )

    # Get category counts by source app
    category_counts = (
        db.query(Category.source_app, func.count(Category.id))
        .group_by(Category.source_app)
        .all()
    )

    # Get brand counts by source app
    brand_counts = (
        db.query(Brand.source_app, func.count(Brand.id))
        .group_by(Brand.source_app)
        .all()
    )

    # Get total price records
    total_price_records = db.query(func.count(PriceRecord.id)).scalar()

    # Get recent scrape jobs
    recent_jobs = (
        db.query(ScrapeJob)
        .order_by(ScrapeJob.created_at.desc())
        .limit(5)
        .all()
    )

    # Get last scrape time per app
    last_scrapes = (
        db.query(ScrapeJob.source_app, func.max(ScrapeJob.completed_at))
        .filter(ScrapeJob.status == "completed")
        .group_by(ScrapeJob.source_app)
        .all()
    )

    return {
        "products": {
            "total": sum(count for _, count in product_counts),
            "by_app": {app: count for app, count in product_counts},
        },
        "categories": {
            "total": sum(count for _, count in category_counts),
            "by_app": {app: count for app, count in category_counts},
        },
        "brands": {
            "total": sum(count for _, count in brand_counts),
            "by_app": {app: count for app, count in brand_counts},
        },
        "price_records": total_price_records,
        "last_scrapes": {app: scrape_time.isoformat() if scrape_time else None for app, scrape_time in last_scrapes},
        "recent_jobs": [
            {
                "id": job.id,
                "source_app": job.source_app,
                "job_type": job.job_type,
                "status": job.status,
                "products_scraped": job.products_scraped,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            }
            for job in recent_jobs
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }
