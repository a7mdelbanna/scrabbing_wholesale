"""Analytics API routes."""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.models.database import Product, PriceRecord, ScrapeJob, Category

router = APIRouter(prefix="/analytics", tags=["Analytics"])


class PriceTrendItem(BaseModel):
    """Price trend data point."""

    date: datetime
    avg_price: float
    min_price: float
    max_price: float
    products_count: int


class PriceTrendResponse(BaseModel):
    """Price trend response."""

    source_app: Optional[str] = None
    period_days: int
    data: List[PriceTrendItem]


class AvailabilityStats(BaseModel):
    """Availability statistics."""

    source_app: str
    total_products: int
    available_products: int
    unavailable_products: int
    availability_percentage: float


class PriceChangeItem(BaseModel):
    """Price change item."""

    product_id: int
    product_name: str
    source_app: str
    old_price: float
    new_price: float
    change_amount: float
    change_percentage: float
    changed_at: datetime


class ScraperPerformance(BaseModel):
    """Scraper performance metrics."""

    source_app: str
    total_jobs: int
    successful_jobs: int
    failed_jobs: int
    avg_products_per_job: float
    avg_duration_seconds: Optional[float] = None
    last_run: Optional[datetime] = None


class CategoryStats(BaseModel):
    """Category statistics."""

    category_id: int
    category_name: str
    source_app: str
    products_count: int
    avg_price: Optional[float] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None


@router.get("/price-trends")
async def get_price_trends(
    period: str = Query(default="30d", description="Time period (7d, 30d, 90d)"),
    source_app: Optional[str] = Query(None, description="Filter by source app"),
    category_id: Optional[int] = Query(None, description="Filter by category"),
    db: Session = Depends(get_db),
) -> PriceTrendResponse:
    """Get price trends over time."""
    # Parse period
    days = int(period.rstrip("d"))
    start_date = datetime.utcnow() - timedelta(days=days)

    query = db.query(
        func.date_trunc("day", PriceRecord.recorded_at).label("date"),
        func.avg(PriceRecord.price).label("avg_price"),
        func.min(PriceRecord.price).label("min_price"),
        func.max(PriceRecord.price).label("max_price"),
        func.count(func.distinct(PriceRecord.product_id)).label("products_count"),
    ).filter(PriceRecord.recorded_at >= start_date)

    if source_app:
        query = query.filter(PriceRecord.source_app == source_app)
    if category_id:
        query = query.join(Product).filter(Product.category_id == category_id)

    query = query.group_by(func.date_trunc("day", PriceRecord.recorded_at))
    query = query.order_by(func.date_trunc("day", PriceRecord.recorded_at))

    results = query.all()

    data = [
        PriceTrendItem(
            date=row.date,
            avg_price=float(row.avg_price),
            min_price=float(row.min_price),
            max_price=float(row.max_price),
            products_count=row.products_count,
        )
        for row in results
    ]

    return PriceTrendResponse(
        source_app=source_app,
        period_days=days,
        data=data,
    )


@router.get("/availability")
async def get_availability_stats(
    db: Session = Depends(get_db),
) -> List[AvailabilityStats]:
    """Get availability statistics by app."""
    # Get latest prices for each product
    subq = (
        db.query(
            PriceRecord.product_id,
            func.max(PriceRecord.recorded_at).label("max_time")
        )
        .group_by(PriceRecord.product_id)
        .subquery()
    )

    latest_prices = (
        db.query(
            Product.source_app,
            PriceRecord.is_available,
            func.count(Product.id).label("count")
        )
        .join(PriceRecord, Product.id == PriceRecord.product_id)
        .join(
            subq,
            (PriceRecord.product_id == subq.c.product_id) &
            (PriceRecord.recorded_at == subq.c.max_time)
        )
        .group_by(Product.source_app, PriceRecord.is_available)
        .all()
    )

    # Aggregate by app
    app_stats: Dict[str, Dict[str, int]] = {}
    for source_app, is_available, count in latest_prices:
        if source_app not in app_stats:
            app_stats[source_app] = {"available": 0, "unavailable": 0}
        if is_available:
            app_stats[source_app]["available"] = count
        else:
            app_stats[source_app]["unavailable"] = count

    return [
        AvailabilityStats(
            source_app=app,
            total_products=stats["available"] + stats["unavailable"],
            available_products=stats["available"],
            unavailable_products=stats["unavailable"],
            availability_percentage=round(
                stats["available"] / (stats["available"] + stats["unavailable"]) * 100, 2
            ) if (stats["available"] + stats["unavailable"]) > 0 else 0,
        )
        for app, stats in app_stats.items()
    ]


@router.get("/scraper-performance")
async def get_scraper_performance(
    db: Session = Depends(get_db),
) -> List[ScraperPerformance]:
    """Get scraper performance metrics by app."""
    from sqlalchemy import case

    # Get job statistics per app
    job_stats = (
        db.query(
            ScrapeJob.source_app,
            func.count(ScrapeJob.id).label("total_jobs"),
            func.sum(case((ScrapeJob.status == "completed", 1), else_=0)).label("successful"),
            func.sum(case((ScrapeJob.status == "failed", 1), else_=0)).label("failed"),
            func.avg(ScrapeJob.products_scraped).label("avg_products"),
            func.max(ScrapeJob.completed_at).label("last_run"),
        )
        .group_by(ScrapeJob.source_app)
        .all()
    )

    return [
        ScraperPerformance(
            source_app=row.source_app,
            total_jobs=row.total_jobs,
            successful_jobs=int(row.successful) if row.successful else 0,
            failed_jobs=int(row.failed) if row.failed else 0,
            avg_products_per_job=float(row.avg_products) if row.avg_products else 0,
            last_run=row.last_run,
        )
        for row in job_stats
    ]


@router.get("/price-changes")
async def get_price_changes(
    hours: int = Query(default=24, ge=1, le=168, description="Hours to look back"),
    source_app: Optional[str] = Query(None, description="Filter by source app"),
    min_change_percent: float = Query(default=5, description="Minimum change percentage"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get recent price changes."""
    # This is a simplified implementation
    # In production, you'd want a more efficient query
    since = datetime.utcnow() - timedelta(hours=hours)

    # Get products with multiple price records in the timeframe
    recent_prices = (
        db.query(PriceRecord)
        .filter(PriceRecord.recorded_at >= since)
        .order_by(PriceRecord.product_id, PriceRecord.recorded_at)
        .all()
    )

    # Group by product and find changes
    changes = []
    product_prices: Dict[int, List[PriceRecord]] = {}
    for pr in recent_prices:
        if pr.product_id not in product_prices:
            product_prices[pr.product_id] = []
        product_prices[pr.product_id].append(pr)

    for product_id, prices in product_prices.items():
        if len(prices) >= 2:
            old_price = float(prices[0].price)
            new_price = float(prices[-1].price)
            if old_price > 0:
                change_pct = abs((new_price - old_price) / old_price * 100)
                if change_pct >= min_change_percent:
                    product = db.query(Product).filter(Product.id == product_id).first()
                    if product and (not source_app or product.source_app == source_app):
                        changes.append({
                            "product_id": product_id,
                            "product_name": product.name,
                            "source_app": product.source_app,
                            "old_price": old_price,
                            "new_price": new_price,
                            "change_amount": new_price - old_price,
                            "change_percentage": round(change_pct, 2),
                            "changed_at": prices[-1].recorded_at,
                        })

    # Sort by change percentage
    changes.sort(key=lambda x: abs(x["change_percentage"]), reverse=True)

    # Paginate
    total = len(changes)
    offset = (page - 1) * per_page
    paginated = changes[offset:offset + per_page]

    return {
        "data": paginated,
        "meta": {
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page if total > 0 else 1,
        }
    }


@router.get("/category-stats")
async def get_category_stats(
    source_app: Optional[str] = Query(None, description="Filter by source app"),
    db: Session = Depends(get_db),
) -> List[CategoryStats]:
    """Get statistics by category."""
    # Get latest price per product
    price_subq = (
        db.query(
            PriceRecord.product_id,
            func.max(PriceRecord.recorded_at).label("max_time")
        )
        .group_by(PriceRecord.product_id)
        .subquery()
    )

    query = (
        db.query(
            Category.id,
            Category.name,
            Category.source_app,
            func.count(Product.id).label("products_count"),
            func.avg(PriceRecord.price).label("avg_price"),
            func.min(PriceRecord.price).label("min_price"),
            func.max(PriceRecord.price).label("max_price"),
        )
        .join(Product, Category.id == Product.category_id)
        .outerjoin(PriceRecord, Product.id == PriceRecord.product_id)
        .outerjoin(
            price_subq,
            (PriceRecord.product_id == price_subq.c.product_id) &
            (PriceRecord.recorded_at == price_subq.c.max_time)
        )
        .group_by(Category.id, Category.name, Category.source_app)
    )

    if source_app:
        query = query.filter(Category.source_app == source_app)

    results = query.all()

    return [
        CategoryStats(
            category_id=row.id,
            category_name=row.name,
            source_app=row.source_app,
            products_count=row.products_count,
            avg_price=float(row.avg_price) if row.avg_price else None,
            min_price=float(row.min_price) if row.min_price else None,
            max_price=float(row.max_price) if row.max_price else None,
        )
        for row in results
    ]
