"""JSON API routes for dashboard data."""
from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select, func, desc
import httpx

from src.database.connection import get_async_session
from src.models.database import Product, Category, PriceRecord, ScrapeJob
from src.models.enums import SourceApp

router = APIRouter()

# Image proxy headers for Ben Soliman
IMAGE_HEADERS = {
    "user-agent": "Dart/3.9 (dart:io)",
    "accept-language": "ar",
    "os": "android",
}


class StatsResponse(BaseModel):
    """Dashboard statistics response."""
    total_products: int
    ben_soliman_products: int
    tager_elsaada_products: int
    total_categories: int
    total_price_records: int
    products_with_offers: int


class PriceHistoryPoint(BaseModel):
    """Single point in price history."""
    date: str
    price: float
    is_available: bool


class PriceHistoryResponse(BaseModel):
    """Price history response for charts."""
    product_id: int
    product_name: str
    source_app: str
    history: List[PriceHistoryPoint]


class ProductResponse(BaseModel):
    """Product response model."""
    id: int
    external_id: str
    name: str
    source_app: str
    image_url: Optional[str]
    current_price: Optional[float]
    is_available: bool

    class Config:
        from_attributes = True


@router.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get dashboard statistics."""
    async with get_async_session() as session:
        total_products = await session.scalar(
            select(func.count(Product.id)).where(Product.is_active == True)
        )

        ben_soliman_count = await session.scalar(
            select(func.count(Product.id)).where(
                Product.source_app == SourceApp.BEN_SOLIMAN.value,
                Product.is_active == True,
            )
        )

        tager_count = await session.scalar(
            select(func.count(Product.id)).where(
                Product.source_app == SourceApp.TAGER_ELSAADA.value,
                Product.is_active == True,
            )
        )

        category_count = await session.scalar(select(func.count(Category.id)))
        price_record_count = await session.scalar(select(func.count(PriceRecord.id)))

        # Products with current offers (discount > 0)
        products_with_offers = await session.scalar(
            select(func.count(func.distinct(PriceRecord.product_id))).where(
                PriceRecord.discount_percentage > 0
            )
        )

    return StatsResponse(
        total_products=total_products or 0,
        ben_soliman_products=ben_soliman_count or 0,
        tager_elsaada_products=tager_count or 0,
        total_categories=category_count or 0,
        total_price_records=price_record_count or 0,
        products_with_offers=products_with_offers or 0,
    )


@router.get("/products/{product_id}/prices", response_model=PriceHistoryResponse)
async def get_price_history(
    product_id: int,
    days: int = Query(30, ge=1, le=365, description="Number of days of history"),
):
    """Get price history for a product (for Chart.js)."""
    async with get_async_session() as session:
        # Get product
        product_result = await session.execute(
            select(Product).where(Product.id == product_id)
        )
        product = product_result.scalar_one_or_none()

        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        # Get price history
        cutoff = datetime.utcnow() - timedelta(days=days)
        prices_result = await session.execute(
            select(PriceRecord)
            .where(
                PriceRecord.product_id == product_id,
                PriceRecord.recorded_at >= cutoff,
            )
            .order_by(PriceRecord.recorded_at)
        )
        prices = list(prices_result.scalars().all())

        history = [
            PriceHistoryPoint(
                date=price.recorded_at.isoformat() if price.recorded_at else "",
                price=float(price.price),
                is_available=price.is_available,
            )
            for price in prices
        ]

    return PriceHistoryResponse(
        product_id=product.id,
        product_name=product.name,
        source_app=product.source_app,
        history=history,
    )


@router.get("/products")
async def get_products(
    source: Optional[str] = Query(None),
    category_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """Get filtered products list (for HTMX)."""
    async with get_async_session() as session:
        query = select(Product).where(Product.is_active == True)

        if source:
            query = query.where(Product.source_app == source)

        if category_id:
            query = query.where(Product.category_id == category_id)

        if search:
            query = query.where(Product.name.ilike(f"%{search}%"))

        # Get total
        count_query = select(func.count()).select_from(query.subquery())
        total = await session.scalar(count_query)

        # Paginate
        query = query.order_by(Product.name).offset((page - 1) * per_page).limit(per_page)
        result = await session.execute(query)
        products = list(result.scalars().all())

        # Get latest prices
        products_data = []
        for product in products:
            price_result = await session.execute(
                select(PriceRecord)
                .where(PriceRecord.product_id == product.id)
                .order_by(desc(PriceRecord.recorded_at))
                .limit(1)
            )
            latest_price = price_result.scalar_one_or_none()

            products_data.append({
                "id": product.id,
                "external_id": product.external_id,
                "name": product.name,
                "source_app": product.source_app,
                "image_url": product.image_url,
                "current_price": float(latest_price.price) if latest_price else None,
                "is_available": latest_price.is_available if latest_price else False,
            })

    return {
        "products": products_data,
        "total": total or 0,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page if total else 1,
    }


@router.get("/comparison/{barcode}")
async def get_comparison(barcode: str):
    """Get price comparison for a specific barcode."""
    async with get_async_session() as session:
        # Get products with this barcode
        products_result = await session.execute(
            select(Product).where(
                Product.barcode == barcode,
                Product.is_active == True,
            )
        )
        products = list(products_result.scalars().all())

        if not products:
            raise HTTPException(status_code=404, detail="No products found with this barcode")

        comparison = {
            "barcode": barcode,
            "ben_soliman": None,
            "tager_elsaada": None,
        }

        for product in products:
            # Get latest price
            price_result = await session.execute(
                select(PriceRecord)
                .where(PriceRecord.product_id == product.id)
                .order_by(desc(PriceRecord.recorded_at))
                .limit(1)
            )
            latest_price = price_result.scalar_one_or_none()

            app_key = (
                "ben_soliman"
                if product.source_app == SourceApp.BEN_SOLIMAN.value
                else "tager_elsaada"
            )
            comparison[app_key] = {
                "product_id": product.id,
                "name": product.name,
                "price": float(latest_price.price) if latest_price else None,
                "is_available": latest_price.is_available if latest_price else False,
                "image_url": product.image_url,
            }

        # Calculate difference if both exist
        if comparison["ben_soliman"] and comparison["tager_elsaada"]:
            bs_price = comparison["ben_soliman"]["price"]
            te_price = comparison["tager_elsaada"]["price"]
            if bs_price and te_price:
                diff = bs_price - te_price
                comparison["difference"] = diff
                comparison["difference_pct"] = (diff / te_price) * 100 if te_price else 0
                comparison["cheaper"] = "ben_soliman" if diff < 0 else "tager_elsaada" if diff > 0 else None

    return comparison


@router.get("/daily-prices/{product_id}")
async def get_daily_prices(
    product_id: int,
    days: int = Query(30, ge=1, le=365),
):
    """Get daily average prices for Chart.js visualization."""
    async with get_async_session() as session:
        product_result = await session.execute(
            select(Product).where(Product.id == product_id)
        )
        product = product_result.scalar_one_or_none()

        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        cutoff = datetime.utcnow() - timedelta(days=days)

        # Get daily aggregates
        result = await session.execute(
            select(
                func.date(PriceRecord.recorded_at).label("date"),
                func.avg(PriceRecord.price).label("avg_price"),
                func.min(PriceRecord.price).label("min_price"),
                func.max(PriceRecord.price).label("max_price"),
            )
            .where(
                PriceRecord.product_id == product_id,
                PriceRecord.recorded_at >= cutoff,
            )
            .group_by(func.date(PriceRecord.recorded_at))
            .order_by(func.date(PriceRecord.recorded_at))
        )

        daily_data = [
            {
                "date": str(row.date),
                "avg_price": float(row.avg_price),
                "min_price": float(row.min_price),
                "max_price": float(row.max_price),
            }
            for row in result.all()
        ]

    return {
        "product_id": product.id,
        "product_name": product.name,
        "daily_prices": daily_data,
    }


@router.get("/image-proxy")
async def image_proxy(url: str):
    """Proxy for fetching product images with proper headers.

    This is needed because the Ben Soliman image server requires specific headers.
    """
    # Only allow proxying from known image hosts
    allowed_hosts = ["37.148.206.212", "41.65.168.38"]

    from urllib.parse import urlparse
    parsed = urlparse(url)

    if parsed.hostname not in allowed_hosts:
        raise HTTPException(status_code=400, detail="Invalid image host")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=IMAGE_HEADERS)

            if response.status_code == 200:
                content_type = response.headers.get("content-type", "image/png")
                return Response(
                    content=response.content,
                    media_type=content_type,
                    headers={"Cache-Control": "public, max-age=86400"}  # Cache for 24 hours
                )
            else:
                raise HTTPException(status_code=404, detail="Image not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch image: {str(e)}")
