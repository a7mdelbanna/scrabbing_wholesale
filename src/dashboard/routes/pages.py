"""HTML page routes for the dashboard."""
import logging
from typing import Optional
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func, desc

from src.database.connection import get_async_session
from src.models.database import Product, Category, PriceRecord, ScrapeJob
from src.models.enums import SourceApp

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Dashboard home page with statistics."""
    templates = request.app.state.templates

    # Default values if database is unavailable
    ben_soliman_count = 0
    tager_count = 0
    category_count = 0
    recent_jobs = []
    price_record_count = 0
    db_error = None

    try:
        async with get_async_session() as session:
            # Get product counts by source app
            ben_soliman_count = await session.scalar(
                select(func.count(Product.id)).where(
                    Product.source_app == SourceApp.BEN_SOLIMAN.value,
                    Product.is_active == True,
                )
            ) or 0
            tager_count = await session.scalar(
                select(func.count(Product.id)).where(
                    Product.source_app == SourceApp.TAGER_ELSAADA.value,
                    Product.is_active == True,
                )
            ) or 0

            # Get category counts
            category_count = await session.scalar(select(func.count(Category.id))) or 0

            # Get recent scrape jobs
            recent_jobs_result = await session.execute(
                select(ScrapeJob)
                .order_by(desc(ScrapeJob.created_at))
                .limit(5)
            )
            recent_jobs = list(recent_jobs_result.scalars().all())

            # Get total price records
            price_record_count = await session.scalar(select(func.count(PriceRecord.id))) or 0
    except Exception as e:
        logger.warning(f"Database error on home page: {e}")
        db_error = "Database not connected. Start PostgreSQL to see data."

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "ben_soliman_count": ben_soliman_count,
            "tager_count": tager_count,
            "category_count": category_count,
            "recent_jobs": recent_jobs,
            "price_record_count": price_record_count,
            "db_error": db_error,
        },
    )


@router.get("/products", response_class=HTMLResponse)
async def products_page(
    request: Request,
    source: Optional[str] = Query(None, description="Filter by source app"),
    category_id: Optional[int] = Query(None, description="Filter by category"),
    available_only: bool = Query(False, description="Show only available products"),
    search: Optional[str] = Query(None, description="Search in product name"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
):
    """Products listing page with filters."""
    templates = request.app.state.templates

    async with get_async_session() as session:
        # Build query
        query = select(Product).where(Product.is_active == True)

        if source:
            query = query.where(Product.source_app == source)

        if category_id:
            query = query.where(Product.category_id == category_id)

        if search:
            query = query.where(Product.name.ilike(f"%{search}%"))

        # Get total count for pagination
        count_query = select(func.count()).select_from(query.subquery())
        total = await session.scalar(count_query)

        # Apply pagination
        query = query.order_by(Product.name).offset((page - 1) * per_page).limit(per_page)

        result = await session.execute(query)
        products = list(result.scalars().all())

        # Get categories for filter dropdown
        categories_result = await session.execute(
            select(Category).order_by(Category.name)
        )
        categories = list(categories_result.scalars().all())

        # Get latest prices for products
        products_with_prices = []
        for product in products:
            price_result = await session.execute(
                select(PriceRecord)
                .where(PriceRecord.product_id == product.id)
                .order_by(desc(PriceRecord.recorded_at))
                .limit(1)
            )
            latest_price = price_result.scalar_one_or_none()
            products_with_prices.append({
                "product": product,
                "latest_price": latest_price,
            })

    total_pages = (total + per_page - 1) // per_page if total else 1

    return templates.TemplateResponse(
        "products.html",
        {
            "request": request,
            "products": products_with_prices,
            "categories": categories,
            "total": total or 0,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "source": source,
            "category_id": category_id,
            "available_only": available_only,
            "search": search or "",
            "source_apps": [
                {"value": SourceApp.BEN_SOLIMAN.value, "label": "بن سليمان"},
                {"value": SourceApp.TAGER_ELSAADA.value, "label": "تاجر السعادة"},
            ],
        },
    )


@router.get("/products/{product_id}", response_class=HTMLResponse)
async def product_detail(request: Request, product_id: int):
    """Product detail page with price history chart."""
    templates = request.app.state.templates

    async with get_async_session() as session:
        # Get product
        product_result = await session.execute(
            select(Product).where(Product.id == product_id)
        )
        product = product_result.scalar_one_or_none()

        if not product:
            return templates.TemplateResponse(
                "404.html",
                {"request": request, "message": "Product not found"},
                status_code=404,
            )

        # Get category
        category = None
        if product.category_id:
            category_result = await session.execute(
                select(Category).where(Category.id == product.category_id)
            )
            category = category_result.scalar_one_or_none()

        # Get latest price
        latest_price_result = await session.execute(
            select(PriceRecord)
            .where(PriceRecord.product_id == product_id)
            .order_by(desc(PriceRecord.recorded_at))
            .limit(1)
        )
        latest_price = latest_price_result.scalar_one_or_none()

        # Check for matching product in other app (by barcode)
        matching_product = None
        if product.barcode:
            other_app = (
                SourceApp.TAGER_ELSAADA.value
                if product.source_app == SourceApp.BEN_SOLIMAN.value
                else SourceApp.BEN_SOLIMAN.value
            )
            matching_result = await session.execute(
                select(Product).where(
                    Product.barcode == product.barcode,
                    Product.source_app == other_app,
                )
            )
            matching_product = matching_result.scalar_one_or_none()

    return templates.TemplateResponse(
        "product_detail.html",
        {
            "request": request,
            "product": product,
            "category": category,
            "latest_price": latest_price,
            "matching_product": matching_product,
        },
    )


@router.get("/comparison", response_class=HTMLResponse)
async def comparison_page(request: Request):
    """Cross-app price comparison page."""
    templates = request.app.state.templates

    async with get_async_session() as session:
        # Find products with barcodes that exist in both apps
        # Subquery to find barcodes in both apps
        subquery = (
            select(Product.barcode)
            .where(
                Product.barcode.isnot(None),
                Product.barcode != "",
                Product.is_active == True,
            )
            .group_by(Product.barcode)
            .having(func.count(func.distinct(Product.source_app)) > 1)
        )

        # Get products with matching barcodes
        products_result = await session.execute(
            select(Product)
            .where(Product.barcode.in_(subquery))
            .order_by(Product.barcode, Product.source_app)
        )
        products = list(products_result.scalars().all())

        # Group by barcode and get prices
        comparisons = {}
        for product in products:
            if product.barcode not in comparisons:
                comparisons[product.barcode] = {
                    "barcode": product.barcode,
                    "ben_soliman": None,
                    "tager_elsaada": None,
                }

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
            comparisons[product.barcode][app_key] = {
                "product": product,
                "price": latest_price,
            }

        # Calculate price differences
        comparison_list = []
        for barcode, data in comparisons.items():
            if data["ben_soliman"] and data["tager_elsaada"]:
                bs_price = data["ben_soliman"]["price"]
                te_price = data["tager_elsaada"]["price"]
                if bs_price and te_price:
                    diff = float(bs_price.price) - float(te_price.price)
                    diff_pct = (diff / float(te_price.price)) * 100 if te_price.price else 0
                    data["difference"] = diff
                    data["difference_pct"] = diff_pct
                    data["cheaper"] = "ben_soliman" if diff < 0 else "tager_elsaada" if diff > 0 else None
            comparison_list.append(data)

    return templates.TemplateResponse(
        "comparison.html",
        {
            "request": request,
            "comparisons": comparison_list,
            "total": len(comparison_list),
        },
    )


@router.get("/jobs", response_class=HTMLResponse)
async def jobs_page(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """Scrape jobs monitoring page."""
    templates = request.app.state.templates

    async with get_async_session() as session:
        # Get total count
        total = await session.scalar(select(func.count(ScrapeJob.id)))

        # Get paginated jobs
        jobs_result = await session.execute(
            select(ScrapeJob)
            .order_by(desc(ScrapeJob.created_at))
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        jobs = list(jobs_result.scalars().all())

    total_pages = (total + per_page - 1) // per_page if total else 1

    return templates.TemplateResponse(
        "jobs.html",
        {
            "request": request,
            "jobs": jobs,
            "total": total or 0,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
        },
    )
