"""Comparison API routes for cross-app price comparison."""
from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from src.api.dependencies import get_db
from src.api.schemas.common import PaginatedResponse, PaginationMeta, PriceInfo
from src.models.database import Product, PriceRecord

router = APIRouter(prefix="/comparison", tags=["Comparison"])


class ProductComparisonItem(BaseModel):
    """Product comparison item from a single app."""

    product_id: int
    source_app: str
    name: str
    name_ar: Optional[str] = None
    barcode: Optional[str] = None
    image_url: Optional[str] = None
    price: Optional[float] = None
    original_price: Optional[float] = None
    discount_percentage: Optional[float] = None
    is_available: bool = True
    last_updated: Optional[datetime] = None


class ComparisonResult(BaseModel):
    """Comparison result for a product across apps."""

    barcode: Optional[str] = None
    primary_name: str
    products: List[ProductComparisonItem]
    lowest_price: Optional[float] = None
    highest_price: Optional[float] = None
    price_difference: Optional[float] = None
    apps_count: int = 0


@router.get("")
async def compare_products(
    apps: Optional[str] = Query(None, description="Comma-separated app names to compare"),
    category_id: Optional[int] = Query(None, description="Filter by category"),
    barcode: Optional[str] = Query(None, description="Filter by barcode"),
    search: Optional[str] = Query(None, description="Search product name"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PaginatedResponse[ComparisonResult]:
    """Compare products across multiple apps."""
    # Parse apps filter
    app_list = apps.split(",") if apps else None

    # Get products with barcodes that exist in multiple apps
    query = db.query(Product).options(
        joinedload(Product.price_records),
    ).filter(Product.barcode.isnot(None))

    if app_list:
        query = query.filter(Product.source_app.in_(app_list))
    if category_id:
        query = query.filter(Product.category_id == category_id)
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            (Product.name.ilike(search_filter)) |
            (Product.name_ar.ilike(search_filter))
        )
    if barcode:
        query = query.filter(Product.barcode == barcode)

    # Group by barcode
    products = query.all()
    barcode_groups: Dict[str, List[Product]] = {}
    for p in products:
        if p.barcode:
            if p.barcode not in barcode_groups:
                barcode_groups[p.barcode] = []
            barcode_groups[p.barcode].append(p)

    # Filter to only products in multiple apps
    multi_app_barcodes = {bc: prods for bc, prods in barcode_groups.items() if len(prods) > 1}

    # Paginate
    total = len(multi_app_barcodes)
    barcodes = list(multi_app_barcodes.keys())
    offset = (page - 1) * per_page
    paginated_barcodes = barcodes[offset:offset + per_page]

    # Build comparison results
    results = []
    for bc in paginated_barcodes:
        prods = multi_app_barcodes[bc]
        items = []
        prices = []

        for p in prods:
            latest_price = p.price_records[0] if p.price_records else None
            price = float(latest_price.price) if latest_price else None

            items.append(ProductComparisonItem(
                product_id=p.id,
                source_app=p.source_app,
                name=p.name,
                name_ar=p.name_ar,
                barcode=p.barcode,
                image_url=p.image_url,
                price=price,
                original_price=float(latest_price.original_price) if latest_price and latest_price.original_price else None,
                discount_percentage=float(latest_price.discount_percentage) if latest_price and latest_price.discount_percentage else None,
                is_available=latest_price.is_available if latest_price else True,
                last_updated=latest_price.recorded_at if latest_price else None,
            ))
            if price:
                prices.append(price)

        lowest = min(prices) if prices else None
        highest = max(prices) if prices else None

        results.append(ComparisonResult(
            barcode=bc,
            primary_name=prods[0].name,
            products=items,
            lowest_price=lowest,
            highest_price=highest,
            price_difference=highest - lowest if lowest and highest else None,
            apps_count=len(prods),
        ))

    meta = PaginationMeta.from_pagination(total, page, per_page)
    return PaginatedResponse(data=results, meta=meta)


@router.get("/by-barcode/{barcode}")
async def compare_by_barcode(
    barcode: str,
    db: Session = Depends(get_db),
) -> ComparisonResult:
    """Get comparison for a specific barcode."""
    products = db.query(Product).options(
        joinedload(Product.price_records),
    ).filter(Product.barcode == barcode).all()

    items = []
    prices = []

    for p in products:
        latest_price = p.price_records[0] if p.price_records else None
        price = float(latest_price.price) if latest_price else None

        items.append(ProductComparisonItem(
            product_id=p.id,
            source_app=p.source_app,
            name=p.name,
            name_ar=p.name_ar,
            barcode=p.barcode,
            image_url=p.image_url,
            price=price,
            original_price=float(latest_price.original_price) if latest_price and latest_price.original_price else None,
            discount_percentage=float(latest_price.discount_percentage) if latest_price and latest_price.discount_percentage else None,
            is_available=latest_price.is_available if latest_price else True,
            last_updated=latest_price.recorded_at if latest_price else None,
        ))
        if price:
            prices.append(price)

    lowest = min(prices) if prices else None
    highest = max(prices) if prices else None

    return ComparisonResult(
        barcode=barcode,
        primary_name=products[0].name if products else "",
        products=items,
        lowest_price=lowest,
        highest_price=highest,
        price_difference=highest - lowest if lowest and highest else None,
        apps_count=len(products),
    )


@router.get("/stats")
async def get_comparison_stats(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get comparison statistics."""
    # Count products with barcodes per app
    barcode_counts = dict(
        db.query(Product.source_app, func.count(Product.id))
        .filter(Product.barcode.isnot(None))
        .group_by(Product.source_app)
        .all()
    )

    # Count unique barcodes
    total_unique_barcodes = (
        db.query(func.count(func.distinct(Product.barcode)))
        .filter(Product.barcode.isnot(None))
        .scalar()
    )

    # Count barcodes in multiple apps
    barcode_app_counts = (
        db.query(Product.barcode, func.count(func.distinct(Product.source_app)))
        .filter(Product.barcode.isnot(None))
        .group_by(Product.barcode)
        .all()
    )
    multi_app_count = sum(1 for _, count in barcode_app_counts if count > 1)

    return {
        "products_with_barcodes": barcode_counts,
        "total_unique_barcodes": total_unique_barcodes,
        "barcodes_in_multiple_apps": multi_app_count,
        "comparison_coverage_percentage": round(multi_app_count / total_unique_barcodes * 100, 2) if total_unique_barcodes else 0,
    }
