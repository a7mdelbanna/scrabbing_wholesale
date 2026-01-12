"""Brands API routes."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from src.api.dependencies import get_db
from src.api.middleware.error_handler import NotFoundError
from src.api.schemas.common import PaginatedResponse, PaginationMeta, BrandInfo
from src.models.database import Brand, Product

router = APIRouter(prefix="/brands", tags=["Brands"])


class BrandResponse(BrandInfo):
    """Brand response with additional fields."""

    source_app: str = Field(..., description="Source application")
    external_id: str = Field(..., description="External ID in source app")
    is_active: bool = Field(default=True, description="Is brand active")
    products_count: int = Field(default=0, description="Number of products")

    class Config:
        from_attributes = True


def build_brand_response(brand: Brand, products_count: int = 0) -> BrandResponse:
    """Build brand response from ORM model."""
    return BrandResponse(
        id=brand.id,
        name=brand.name,
        name_ar=brand.name_ar,
        image_url=brand.image_url,
        source_app=brand.source_app,
        external_id=brand.external_id,
        is_active=brand.is_active,
        products_count=products_count,
    )


@router.get("", response_model=PaginatedResponse[BrandResponse])
async def list_brands(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    source_app: Optional[str] = Query(None, description="Filter by source app"),
    search: Optional[str] = Query(None, description="Search in brand name"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: Session = Depends(get_db),
):
    """List brands with pagination."""
    query = db.query(Brand)

    if source_app:
        query = query.filter(Brand.source_app == source_app)
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            (Brand.name.ilike(search_filter)) |
            (Brand.name_ar.ilike(search_filter))
        )
    if is_active is not None:
        query = query.filter(Brand.is_active == is_active)

    total = query.count()

    offset = (page - 1) * per_page
    brands = (
        query
        .order_by(Brand.name)
        .offset(offset)
        .limit(per_page)
        .all()
    )

    # Get product counts
    brand_ids = [b.id for b in brands]
    product_counts = dict(
        db.query(Product.brand_id, func.count(Product.id))
        .filter(Product.brand_id.in_(brand_ids))
        .group_by(Product.brand_id)
        .all()
    ) if brand_ids else {}

    items = [
        build_brand_response(b, product_counts.get(b.id, 0))
        for b in brands
    ]
    meta = PaginationMeta.from_pagination(total, page, per_page)

    return PaginatedResponse(data=items, meta=meta)


@router.get("/{brand_id}", response_model=BrandResponse)
async def get_brand(
    brand_id: int,
    db: Session = Depends(get_db),
):
    """Get brand details by ID."""
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise NotFoundError("Brand", brand_id)

    # Get product count
    products_count = (
        db.query(func.count(Product.id))
        .filter(Product.brand_id == brand_id)
        .scalar()
    )

    return build_brand_response(brand, products_count)


@router.get("/{brand_id}/products")
async def get_brand_products(
    brand_id: int,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get products for a brand."""
    from src.api.routes.products import build_product_summary, ProductSummary

    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise NotFoundError("Brand", brand_id)

    query = db.query(Product).options(
        joinedload(Product.category),
        joinedload(Product.brand_rel),
        joinedload(Product.price_records),
        joinedload(Product.units),
    ).filter(Product.brand_id == brand_id)

    total = query.count()

    offset = (page - 1) * per_page
    products = (
        query
        .order_by(Product.name)
        .offset(offset)
        .limit(per_page)
        .all()
    )

    items = [build_product_summary(p) for p in products]
    meta = PaginationMeta.from_pagination(total, page, per_page)

    return PaginatedResponse[ProductSummary](data=items, meta=meta)
