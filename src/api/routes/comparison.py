"""Comparison API routes for cross-app price comparison."""
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, and_
from sqlalchemy.orm import Session, joinedload

from src.api.dependencies import get_db
from src.api.schemas.common import PaginatedResponse, PaginationMeta, PriceInfo
from src.models.database import Product, PriceRecord, ProductUnit, ProductLink

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


class UnitComparisonInfo(BaseModel):
    """Unit info with price and availability for comparison."""
    unit_id: int
    name: str
    name_ar: Optional[str] = None
    factor: int = 1
    barcode: Optional[str] = None
    price: Optional[float] = None
    original_price: Optional[float] = None
    is_available: bool = True
    price_per_base: Optional[float] = None  # Normalized price (price/factor)
    is_linked: bool = False
    linked_to_unit_id: Optional[int] = None
    link_id: Optional[int] = None


class MultiAppComparisonItem(BaseModel):
    """Single app's product in the comparison matrix with units."""
    product_id: Optional[int] = None
    name: Optional[str] = None
    image_url: Optional[str] = None
    barcode: Optional[str] = None
    is_linked: bool = False
    link_id: Optional[int] = None
    units: List[UnitComparisonInfo] = []
    # Aggregate availability (True if any unit is available)
    has_available_units: bool = True
    # Best price among units (lowest price_per_base)
    best_price: Optional[float] = None
    best_unit_id: Optional[int] = None


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
    # Best deal info (app with lowest normalized price)
    best_deal_app: Optional[str] = None
    best_deal_price: Optional[float] = None


def _get_units_with_prices(db: Session, product_id: int, unit_links: Dict[int, Tuple[int, int]] = None) -> List[UnitComparisonInfo]:
    """Get all units for a product with their latest prices."""
    units = db.query(ProductUnit).filter(
        ProductUnit.product_id == product_id,
        ProductUnit.is_active == True,
    ).order_by(ProductUnit.factor).all()

    unit_links = unit_links or {}
    result = []

    for unit in units:
        # Get latest price for this unit
        latest_price = db.query(PriceRecord).filter(
            PriceRecord.product_id == product_id,
            PriceRecord.unit_id == unit.id,
        ).order_by(PriceRecord.recorded_at.desc()).first()

        # If no unit-specific price, try product-level price
        if not latest_price:
            latest_price = db.query(PriceRecord).filter(
                PriceRecord.product_id == product_id,
                PriceRecord.unit_id == None,
            ).order_by(PriceRecord.recorded_at.desc()).first()

        price = float(latest_price.price) if latest_price else None
        price_per_base = price / unit.factor if price and unit.factor else price

        # Check if this unit is linked
        linked_info = unit_links.get(unit.id)

        result.append(UnitComparisonInfo(
            unit_id=unit.id,
            name=unit.name,
            name_ar=unit.name_ar,
            factor=unit.factor,
            barcode=unit.barcode,
            price=price,
            original_price=float(latest_price.original_price) if latest_price and latest_price.original_price else None,
            is_available=latest_price.is_available if latest_price else True,
            price_per_base=round(price_per_base, 2) if price_per_base else None,
            is_linked=linked_info is not None,
            linked_to_unit_id=linked_info[0] if linked_info else None,
            link_id=linked_info[1] if linked_info else None,
        ))

    # If no units found, create a "default" unit from product-level price
    if not result:
        latest_price = db.query(PriceRecord).filter(
            PriceRecord.product_id == product_id,
        ).order_by(PriceRecord.recorded_at.desc()).first()

        price = float(latest_price.price) if latest_price else None
        result.append(UnitComparisonInfo(
            unit_id=0,  # Virtual unit
            name="قطعة",
            factor=1,
            price=price,
            original_price=float(latest_price.original_price) if latest_price and latest_price.original_price else None,
            is_available=latest_price.is_available if latest_price else True,
            price_per_base=price,
        ))

    return result


def _build_app_item(
    db: Session,
    product: Product,
    is_linked: bool = False,
    link_id: Optional[int] = None,
    unit_links: Dict[int, Tuple[int, int]] = None,
) -> MultiAppComparisonItem:
    """Build a MultiAppComparisonItem with units for a product."""
    units = _get_units_with_prices(db, product.id, unit_links)

    # Calculate aggregate availability
    has_available = any(u.is_available for u in units)

    # Find best price (lowest price_per_base)
    available_units = [u for u in units if u.is_available and u.price_per_base]
    best_price = None
    best_unit_id = None
    if available_units:
        best_unit = min(available_units, key=lambda u: u.price_per_base)
        best_price = best_unit.price_per_base
        best_unit_id = best_unit.unit_id

    return MultiAppComparisonItem(
        product_id=product.id,
        name=product.name,
        image_url=product.image_url,
        barcode=product.barcode,
        is_linked=is_linked,
        link_id=link_id,
        units=units,
        has_available_units=has_available,
        best_price=best_price,
        best_unit_id=best_unit_id,
    )


@router.get("/matrix", response_model=PaginatedResponse[MultiAppComparisonRow])
async def get_comparison_matrix(
    source_app: Optional[str] = Query(None, description="Primary app to show products from"),
    search: Optional[str] = Query(None, description="Search product name"),
    show_linked_only: bool = Query(False, description="Only show products with links"),
    show_unlinked_only: bool = Query(False, description="Only show products without full links"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PaginatedResponse[MultiAppComparisonRow]:
    """
    Get multi-app comparison matrix showing all 4 apps with unit-level details.

    Returns products with columns for each app, showing:
    - Product info with all units and their prices
    - Availability status per unit
    - Normalized price (price per base unit) for fair comparison
    - Empty if product doesn't exist in that app
    """
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

    # Get all product links (including unit-level links)
    all_links = db.query(ProductLink).filter(ProductLink.is_active == True).all()

    # Build link maps: product-level and unit-level
    product_link_map: Dict[int, List[Tuple[int, int]]] = {}  # product_id -> [(linked_product_id, link_id)]
    unit_link_map: Dict[int, Dict[int, Tuple[int, int]]] = {}  # product_id -> {unit_id: (linked_unit_id, link_id)}

    for link in all_links:
        # Product-level links
        if link.product_a_id not in product_link_map:
            product_link_map[link.product_a_id] = []
        if link.product_b_id not in product_link_map:
            product_link_map[link.product_b_id] = []
        product_link_map[link.product_a_id].append((link.product_b_id, link.id))
        product_link_map[link.product_b_id].append((link.product_a_id, link.id))

        # Unit-level links
        if link.unit_a_id and link.unit_b_id:
            if link.product_a_id not in unit_link_map:
                unit_link_map[link.product_a_id] = {}
            if link.product_b_id not in unit_link_map:
                unit_link_map[link.product_b_id] = {}
            unit_link_map[link.product_a_id][link.unit_a_id] = (link.unit_b_id, link.id)
            unit_link_map[link.product_b_id][link.unit_b_id] = (link.unit_a_id, link.id)

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
        all_best_prices: List[Tuple[str, float]] = []  # [(app, best_price)]

        # Find products by barcode or by links
        linked_product_ids = [pid for pid, _ in product_link_map.get(primary.id, [])]
        link_ids = {pid: lid for pid, lid in product_link_map.get(primary.id, [])}

        for app in ALL_APPS:
            item = None
            matched_product = None
            is_linked = False
            link_id = None

            if app == primary.source_app:
                # This is the primary product's app
                matched_product = primary
                is_linked = True
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
                        matched_product = barcode_match
                        is_linked = True

                # 2. By product links
                if not matched_product and linked_product_ids:
                    for linked_id in linked_product_ids:
                        linked_product = db.query(Product).filter(
                            Product.id == linked_id,
                            Product.source_app == app,
                        ).first()
                        if linked_product:
                            matched_product = linked_product
                            is_linked = True
                            link_id = link_ids.get(linked_product.id)
                            break

            if matched_product:
                # Get unit links for this product
                unit_links = unit_link_map.get(matched_product.id, {})
                item = _build_app_item(db, matched_product, is_linked, link_id, unit_links)

                if item.best_price:
                    all_best_prices.append((app, item.best_price))

            apps_data[app] = item

        # Set app columns
        row.ben_soliman = apps_data.get("ben_soliman")
        row.tager_elsaada = apps_data.get("tager_elsaada")
        row.el_rabie = apps_data.get("el_rabie")
        row.gomla_shoaib = apps_data.get("gomla_shoaib")

        # Calculate stats
        row.apps_with_product = sum(1 for v in apps_data.values() if v is not None)

        if all_best_prices:
            prices_only = [p for _, p in all_best_prices]
            row.lowest_price = min(prices_only)
            row.highest_price = max(prices_only)
            # Find best deal
            best_app, best_price = min(all_best_prices, key=lambda x: x[1])
            row.best_deal_app = best_app
            row.best_deal_price = best_price

        # Apply filters
        if show_linked_only and row.apps_with_product < 2:
            continue
        if show_unlinked_only and row.apps_with_product >= 4:
            continue

        results.append(row)

    meta = PaginationMeta.from_pagination(total, page, per_page)
    return PaginatedResponse(data=results, meta=meta)
