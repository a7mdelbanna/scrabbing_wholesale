"""Products API routes."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from src.api.dependencies import get_db
from src.api.middleware.error_handler import NotFoundError
from src.api.schemas.common import (
    PaginatedResponse,
    PaginationMeta,
    PriceInfo,
    UnitInfo,
    CategoryInfo,
    BrandInfo,
)
from src.api.schemas.products import (
    ProductSummary,
    ProductDetail,
    ProductUpdate,
    PriceHistoryItem,
)
from src.models.database import Product, PriceRecord, ProductUnit, Category, Brand

router = APIRouter(prefix="/products", tags=["Products"])


def build_product_summary(product: Product) -> ProductSummary:
    """Build product summary from ORM model."""
    # Get current price
    current_price = None
    if product.price_records:
        latest = product.price_records[0]
        current_price = PriceInfo(
            price=float(latest.price),
            original_price=float(latest.original_price) if latest.original_price else None,
            discount_percentage=float(latest.discount_percentage) if latest.discount_percentage else None,
            currency=latest.currency,
            is_available=latest.is_available,
            recorded_at=latest.recorded_at,
        )

    # Get category info
    category_info = None
    if product.category:
        category_info = CategoryInfo(
            id=product.category.id,
            name=product.category.name,
            name_ar=product.category.name_ar,
            image_url=product.category.image_url,
        )

    # Get brand info
    brand_info = None
    if product.brand_rel:
        brand_info = BrandInfo(
            id=product.brand_rel.id,
            name=product.brand_rel.name,
            name_ar=product.brand_rel.name_ar,
            image_url=product.brand_rel.image_url,
        )

    return ProductSummary(
        id=product.id,
        source_app=product.source_app,
        external_id=product.external_id,
        name=product.name,
        name_ar=product.name_ar,
        sku=product.sku,
        barcode=product.barcode,
        image_url=product.image_url,
        category=category_info,
        brand=brand_info,
        current_price=current_price,
        units_count=len(product.units) if product.units else 0,
        is_active=product.is_active,
        last_seen_at=product.last_seen_at,
    )


def build_product_detail(product: Product) -> ProductDetail:
    """Build product detail from ORM model."""
    summary = build_product_summary(product)

    # Build units info with prices
    units_info = []
    for unit in product.units or []:
        # Get latest price for this unit
        unit_price = None
        for pr in product.price_records or []:
            if pr.unit_id == unit.id:
                unit_price = PriceInfo(
                    price=float(pr.price),
                    original_price=float(pr.original_price) if pr.original_price else None,
                    discount_percentage=float(pr.discount_percentage) if pr.discount_percentage else None,
                    currency=pr.currency,
                    is_available=pr.is_available,
                    recorded_at=pr.recorded_at,
                )
                break

        units_info.append(UnitInfo(
            id=unit.id,
            external_id=unit.external_id,
            name=unit.name,
            name_ar=unit.name_ar,
            factor=unit.factor,
            is_base_unit=unit.is_base_unit,
            barcode=unit.barcode,
            current_price=unit_price,
        ))

    return ProductDetail(
        **summary.model_dump(),
        description=product.description,
        description_ar=product.description_ar,
        additional_images=product.additional_images,
        unit_type=product.unit_type,
        unit_value=float(product.unit_value) if product.unit_value else None,
        min_order_quantity=product.min_order_quantity,
        units=units_info,
        first_seen_at=product.first_seen_at,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


@router.get("", response_model=PaginatedResponse[ProductSummary])
async def list_products(
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=50, ge=1, le=100, description="Items per page"),
    source_app: Optional[str] = Query(None, description="Filter by source app"),
    category_id: Optional[int] = Query(None, description="Filter by category ID"),
    brand_id: Optional[int] = Query(None, description="Filter by brand ID"),
    search: Optional[str] = Query(None, description="Search in name"),
    barcode: Optional[str] = Query(None, description="Filter by barcode"),
    sku: Optional[str] = Query(None, description="Filter by SKU"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    min_price: Optional[float] = Query(None, description="Minimum price"),
    max_price: Optional[float] = Query(None, description="Maximum price"),
    sort_by: str = Query(default="name", description="Sort field"),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$", description="Sort order"),
    db: Session = Depends(get_db),
):
    """List products with filters and pagination."""
    query = db.query(Product).options(
        joinedload(Product.category),
        joinedload(Product.brand_rel),
        joinedload(Product.price_records),
        joinedload(Product.units),
    )

    # Apply filters
    if source_app:
        query = query.filter(Product.source_app == source_app)
    if category_id:
        query = query.filter(Product.category_id == category_id)
    if brand_id:
        query = query.filter(Product.brand_id == brand_id)
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            or_(
                Product.name.ilike(search_filter),
                Product.name_ar.ilike(search_filter),
            )
        )
    if barcode:
        query = query.filter(Product.barcode == barcode)
    if sku:
        query = query.filter(Product.sku == sku)
    if is_active is not None:
        query = query.filter(Product.is_active == is_active)

    # Price filters via subquery
    if min_price is not None or max_price is not None:
        # Join with latest price
        price_subq = (
            db.query(
                PriceRecord.product_id,
                func.max(PriceRecord.recorded_at).label("max_time")
            )
            .group_by(PriceRecord.product_id)
            .subquery()
        )
        latest_prices = (
            db.query(PriceRecord)
            .join(
                price_subq,
                (PriceRecord.product_id == price_subq.c.product_id) &
                (PriceRecord.recorded_at == price_subq.c.max_time)
            )
        )
        if min_price is not None:
            latest_prices = latest_prices.filter(PriceRecord.price >= min_price)
        if max_price is not None:
            latest_prices = latest_prices.filter(PriceRecord.price <= max_price)

        product_ids = [pr.product_id for pr in latest_prices.all()]
        query = query.filter(Product.id.in_(product_ids))

    # Get total count
    total = query.count()

    # Apply sorting
    sort_column = getattr(Product, sort_by, Product.name)
    if sort_order == "desc":
        sort_column = sort_column.desc()
    query = query.order_by(sort_column)

    # Apply pagination
    offset = (page - 1) * per_page
    products = query.offset(offset).limit(per_page).all()

    # Build response
    items = [build_product_summary(p) for p in products]
    meta = PaginationMeta.from_pagination(total, page, per_page)

    return PaginatedResponse(data=items, meta=meta)


@router.get("/search")
async def search_products(
    query: str = Query(..., min_length=2, description="Search query"),
    source_app: Optional[str] = Query(None, description="Filter by source app"),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum results"),
    db: Session = Depends(get_db),
) -> List[ProductSummary]:
    """Full-text search for products."""
    search_filter = f"%{query}%"

    db_query = db.query(Product).options(
        joinedload(Product.category),
        joinedload(Product.brand_rel),
        joinedload(Product.price_records),
        joinedload(Product.units),
    ).filter(
        or_(
            Product.name.ilike(search_filter),
            Product.name_ar.ilike(search_filter),
            Product.barcode.ilike(search_filter),
            Product.sku.ilike(search_filter),
        )
    )

    if source_app:
        db_query = db_query.filter(Product.source_app == source_app)

    products = db_query.limit(limit).all()
    return [build_product_summary(p) for p in products]


@router.get("/by-barcode/{barcode}")
async def get_product_by_barcode(
    barcode: str,
    source_app: Optional[str] = Query(None, description="Filter by source app"),
    db: Session = Depends(get_db),
) -> List[ProductSummary]:
    """Get products by barcode (may return multiple from different apps)."""
    query = db.query(Product).options(
        joinedload(Product.category),
        joinedload(Product.brand_rel),
        joinedload(Product.price_records),
        joinedload(Product.units),
    ).filter(Product.barcode == barcode)

    if source_app:
        query = query.filter(Product.source_app == source_app)

    products = query.all()
    return [build_product_summary(p) for p in products]


@router.get("/{product_id}", response_model=ProductDetail)
async def get_product(
    product_id: int,
    db: Session = Depends(get_db),
):
    """Get product details by ID."""
    product = db.query(Product).options(
        joinedload(Product.category),
        joinedload(Product.brand_rel),
        joinedload(Product.price_records),
        joinedload(Product.units),
    ).filter(Product.id == product_id).first()

    if not product:
        raise NotFoundError("Product", product_id)

    return build_product_detail(product)


@router.patch("/{product_id}", response_model=ProductDetail)
async def update_product(
    product_id: int,
    update_data: ProductUpdate,
    db: Session = Depends(get_db),
):
    """Update product metadata."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise NotFoundError("Product", product_id)

    # Update fields that were provided
    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)

    # Reload with relationships
    product = db.query(Product).options(
        joinedload(Product.category),
        joinedload(Product.brand_rel),
        joinedload(Product.price_records),
        joinedload(Product.units),
    ).filter(Product.id == product_id).first()

    return build_product_detail(product)


@router.get("/{product_id}/prices", response_model=PaginatedResponse[PriceHistoryItem])
async def get_product_prices(
    product_id: int,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    unit_id: Optional[int] = Query(None, description="Filter by unit ID"),
    db: Session = Depends(get_db),
):
    """Get price history for a product."""
    # Verify product exists
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise NotFoundError("Product", product_id)

    query = db.query(PriceRecord).filter(PriceRecord.product_id == product_id)

    if unit_id is not None:
        query = query.filter(PriceRecord.unit_id == unit_id)

    total = query.count()

    offset = (page - 1) * per_page
    records = (
        query
        .options(joinedload(PriceRecord.unit))
        .order_by(PriceRecord.recorded_at.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )

    items = [
        PriceHistoryItem(
            id=r.id,
            price=float(r.price),
            original_price=float(r.original_price) if r.original_price else None,
            discount_percentage=float(r.discount_percentage) if r.discount_percentage else None,
            currency=r.currency,
            is_available=r.is_available,
            unit_id=r.unit_id,
            unit_name=r.unit.name if r.unit else None,
            recorded_at=r.recorded_at,
        )
        for r in records
    ]

    meta = PaginationMeta.from_pagination(total, page, per_page)
    return PaginatedResponse(data=items, meta=meta)


@router.get("/{product_id}/units")
async def get_product_units(
    product_id: int,
    db: Session = Depends(get_db),
) -> List[UnitInfo]:
    """Get all units for a product with current prices."""
    product = db.query(Product).options(
        joinedload(Product.units),
        joinedload(Product.price_records),
    ).filter(Product.id == product_id).first()

    if not product:
        raise NotFoundError("Product", product_id)

    units_info = []
    for unit in product.units or []:
        # Get latest price for this unit
        unit_price = None
        for pr in product.price_records or []:
            if pr.unit_id == unit.id:
                unit_price = PriceInfo(
                    price=float(pr.price),
                    original_price=float(pr.original_price) if pr.original_price else None,
                    discount_percentage=float(pr.discount_percentage) if pr.discount_percentage else None,
                    currency=pr.currency,
                    is_available=pr.is_available,
                    recorded_at=pr.recorded_at,
                )
                break

        units_info.append(UnitInfo(
            id=unit.id,
            external_id=unit.external_id,
            name=unit.name,
            name_ar=unit.name_ar,
            factor=unit.factor,
            is_base_unit=unit.is_base_unit,
            barcode=unit.barcode,
            current_price=unit_price,
        ))

    return units_info
