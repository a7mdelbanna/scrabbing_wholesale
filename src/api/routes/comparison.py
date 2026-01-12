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


class MultiAppComparisonItem(BaseModel):
    """Single app's product in the comparison matrix."""
    product_id: Optional[int] = None
    name: Optional[str] = None
    price: Optional[float] = None
    is_available: bool = True
    image_url: Optional[str] = None
    barcode: Optional[str] = None
    is_linked: bool = False
    link_id: Optional[int] = None


class MultiAppComparisonRow(BaseModel):
    """A row in the multi-app comparison matrix."""
    primary_product_id: int
    primary_name: str
    primary_app: str
    barcode: Optional[str] = None
    ben_soliman: Optional[MultiAppComparisonItem] = None
    tager_elsaada: Optional[MultiAppComparisonItem] = None
    el_rabie: Optional[MultiAppComparisonItem] = None
    gomla_shoaib: Optional[MultiAppComparisonItem] = None
    lowest_price: Optional[float] = None
    highest_price: Optional[float] = None
    apps_with_product: int = 1


@router.get("/matrix", response_model=PaginatedResponse[MultiAppComparisonRow])
async def get_comparison_matrix(
    source_app: Optional[str] = Query(None, description="Primary app to show products from"),
    search: Optional[str] = Query(None, description="Search product name"),
    show_linked_only: bool = Query(False, description="Only show products with links"),
    show_unlinked_only: bool = Query(False, description="Only show products without full links"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PaginatedResponse[MultiAppComparisonRow]:
    """
    Get multi-app comparison matrix showing all 4 apps.

    Returns products with columns for each app, showing:
    - Product info if it exists (by barcode or link)
    - Empty if product doesn't exist in that app
    """
    from src.models.database import ProductLink

    ALL_APPS = ["ben_soliman", "tager_elsaada", "el_rabie", "gomla_shoaib"]

    # Build base query for primary products
    query = db.query(Product).filter(Product.is_active == True)

    if source_app:
        query = query.filter(Product.source_app == source_app)

    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            (Product.name.ilike(search_filter)) |
            (Product.name_ar.ilike(search_filter)) |
            (Product.barcode.ilike(search_filter))
        )

    # Get total count
    total = query.count()

    # Apply pagination
    offset = (page - 1) * per_page
    primary_products = query.order_by(Product.name).offset(offset).limit(per_page).all()

    # Get all product links
    all_links = db.query(ProductLink).filter(ProductLink.is_active == True).all()
    link_map: Dict[int, List[Tuple[int, int]]] = {}  # product_id -> [(linked_product_id, link_id)]
    for link in all_links:
        if link.product_a_id not in link_map:
            link_map[link.product_a_id] = []
        if link.product_b_id not in link_map:
            link_map[link.product_b_id] = []
        link_map[link.product_a_id].append((link.product_b_id, link.id))
        link_map[link.product_b_id].append((link.product_a_id, link.id))

    # Build comparison rows
    results = []
    for primary in primary_products:
        row = MultiAppComparisonRow(
            primary_product_id=primary.id,
            primary_name=primary.name,
            primary_app=primary.source_app,
            barcode=primary.barcode,
        )

        # Get products in each app
        apps_data: Dict[str, MultiAppComparisonItem] = {}
        prices = []

        # Find products by barcode or by links
        linked_product_ids = [pid for pid, _ in link_map.get(primary.id, [])]
        link_ids = {pid: lid for pid, lid in link_map.get(primary.id, [])}

        for app in ALL_APPS:
            item = None

            if app == primary.source_app:
                # This is the primary product's app
                latest_price = db.query(PriceRecord).filter(
                    PriceRecord.product_id == primary.id
                ).order_by(PriceRecord.recorded_at.desc()).first()

                price = float(latest_price.price) if latest_price else None
                item = MultiAppComparisonItem(
                    product_id=primary.id,
                    name=primary.name,
                    price=price,
                    is_available=latest_price.is_available if latest_price else True,
                    image_url=primary.image_url,
                    barcode=primary.barcode,
                    is_linked=True,  # Primary product
                )
                if price:
                    prices.append(price)
            else:
                # Look for matching product in this app
                # 1. By barcode
                if primary.barcode:
                    barcode_match = db.query(Product).filter(
                        Product.source_app == app,
                        Product.barcode == primary.barcode,
                        Product.is_active == True,
                    ).first()
                    if barcode_match:
                        latest_price = db.query(PriceRecord).filter(
                            PriceRecord.product_id == barcode_match.id
                        ).order_by(PriceRecord.recorded_at.desc()).first()

                        price = float(latest_price.price) if latest_price else None
                        item = MultiAppComparisonItem(
                            product_id=barcode_match.id,
                            name=barcode_match.name,
                            price=price,
                            is_available=latest_price.is_available if latest_price else True,
                            image_url=barcode_match.image_url,
                            barcode=barcode_match.barcode,
                            is_linked=True,
                        )
                        if price:
                            prices.append(price)

                # 2. By product links
                if not item and linked_product_ids:
                    for linked_id in linked_product_ids:
                        linked_product = db.query(Product).filter(
                            Product.id == linked_id,
                            Product.source_app == app,
                        ).first()
                        if linked_product:
                            latest_price = db.query(PriceRecord).filter(
                                PriceRecord.product_id == linked_product.id
                            ).order_by(PriceRecord.recorded_at.desc()).first()

                            price = float(latest_price.price) if latest_price else None
                            item = MultiAppComparisonItem(
                                product_id=linked_product.id,
                                name=linked_product.name,
                                price=price,
                                is_available=latest_price.is_available if latest_price else True,
                                image_url=linked_product.image_url,
                                barcode=linked_product.barcode,
                                is_linked=True,
                                link_id=link_ids.get(linked_product.id),
                            )
                            if price:
                                prices.append(price)
                            break

            apps_data[app] = item

        # Set app columns
        row.ben_soliman = apps_data.get("ben_soliman")
        row.tager_elsaada = apps_data.get("tager_elsaada")
        row.el_rabie = apps_data.get("el_rabie")
        row.gomla_shoaib = apps_data.get("gomla_shoaib")

        # Calculate stats
        row.apps_with_product = sum(1 for v in apps_data.values() if v is not None)
        row.lowest_price = min(prices) if prices else None
        row.highest_price = max(prices) if prices else None

        # Apply filters
        if show_linked_only and row.apps_with_product < 2:
            continue
        if show_unlinked_only and row.apps_with_product >= 4:
            continue

        results.append(row)

    meta = PaginationMeta.from_pagination(total, page, per_page)
    return PaginatedResponse(data=results, meta=meta)
