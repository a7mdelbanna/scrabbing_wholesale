"""Offers API routes."""
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, and_
from sqlalchemy.orm import Session, joinedload

from src.api.dependencies import get_db
from src.api.middleware.error_handler import NotFoundError
from src.api.schemas.common import PaginatedResponse, PaginationMeta
from src.models.database import Offer, Product

router = APIRouter(prefix="/offers", tags=["Offers"])


class OfferResponse(BaseModel):
    """Offer response schema."""

    id: int = Field(..., description="Offer ID")
    source_app: str = Field(..., description="Source application")
    external_id: str = Field(..., description="External ID")
    product_id: Optional[int] = Field(None, description="Linked product ID")
    product_name: Optional[str] = Field(None, description="Product name")
    title: str = Field(..., description="Offer title")
    title_ar: Optional[str] = Field(None, description="Arabic title")
    description: Optional[str] = Field(None, description="Offer description")
    description_ar: Optional[str] = Field(None, description="Arabic description")
    discount_type: Optional[str] = Field(None, description="Discount type")
    discount_value: Optional[float] = Field(None, description="Discount value")
    start_date: Optional[datetime] = Field(None, description="Start date")
    end_date: Optional[datetime] = Field(None, description="End date")
    is_active: bool = Field(default=True, description="Is offer active")
    first_seen_at: Optional[datetime] = Field(None, description="First seen timestamp")
    last_seen_at: Optional[datetime] = Field(None, description="Last seen timestamp")

    class Config:
        from_attributes = True


@router.get("", response_model=PaginatedResponse[OfferResponse])
async def list_offers(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    source_app: Optional[str] = Query(None, description="Filter by source app"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    discount_type: Optional[str] = Query(None, description="Filter by discount type"),
    db: Session = Depends(get_db),
):
    """List offers with filters and pagination."""
    query = db.query(Offer).options(joinedload(Offer.product))

    if source_app:
        query = query.filter(Offer.source_app == source_app)
    if is_active is not None:
        if is_active:
            now = datetime.utcnow()
            query = query.filter(
                Offer.is_active == True,
                or_(Offer.end_date.is_(None), Offer.end_date >= now)
            )
        else:
            query = query.filter(Offer.is_active == False)
    if discount_type:
        query = query.filter(Offer.discount_type == discount_type)

    total = query.count()

    offset = (page - 1) * per_page
    offers = (
        query
        .order_by(Offer.created_at.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )

    items = [
        OfferResponse(
            id=o.id,
            source_app=o.source_app,
            external_id=o.external_id,
            product_id=o.product_id,
            product_name=o.product.name if o.product else None,
            title=o.title,
            title_ar=o.title_ar,
            description=o.description,
            description_ar=o.description_ar,
            discount_type=o.discount_type,
            discount_value=float(o.discount_value) if o.discount_value else None,
            start_date=o.start_date,
            end_date=o.end_date,
            is_active=o.is_active,
            first_seen_at=o.first_seen_at,
            last_seen_at=o.last_seen_at,
        )
        for o in offers
    ]

    meta = PaginationMeta.from_pagination(total, page, per_page)
    return PaginatedResponse(data=items, meta=meta)


@router.get("/{offer_id}", response_model=OfferResponse)
async def get_offer(
    offer_id: int,
    db: Session = Depends(get_db),
):
    """Get offer details by ID."""
    offer = db.query(Offer).options(joinedload(Offer.product)).filter(Offer.id == offer_id).first()
    if not offer:
        raise NotFoundError("Offer", offer_id)

    return OfferResponse(
        id=offer.id,
        source_app=offer.source_app,
        external_id=offer.external_id,
        product_id=offer.product_id,
        product_name=offer.product.name if offer.product else None,
        title=offer.title,
        title_ar=offer.title_ar,
        description=offer.description,
        description_ar=offer.description_ar,
        discount_type=offer.discount_type,
        discount_value=float(offer.discount_value) if offer.discount_value else None,
        start_date=offer.start_date,
        end_date=offer.end_date,
        is_active=offer.is_active,
        first_seen_at=offer.first_seen_at,
        last_seen_at=offer.last_seen_at,
    )


@router.get("/by-product/{product_id}")
async def get_product_offers(
    product_id: int,
    include_expired: bool = Query(default=False, description="Include expired offers"),
    db: Session = Depends(get_db),
) -> List[OfferResponse]:
    """Get offers for a specific product."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise NotFoundError("Product", product_id)

    query = db.query(Offer).filter(Offer.product_id == product_id)

    if not include_expired:
        now = datetime.utcnow()
        query = query.filter(
            Offer.is_active == True,
            or_(Offer.end_date.is_(None), Offer.end_date >= now)
        )

    offers = query.order_by(Offer.created_at.desc()).all()

    return [
        OfferResponse(
            id=o.id,
            source_app=o.source_app,
            external_id=o.external_id,
            product_id=o.product_id,
            product_name=product.name,
            title=o.title,
            title_ar=o.title_ar,
            description=o.description,
            description_ar=o.description_ar,
            discount_type=o.discount_type,
            discount_value=float(o.discount_value) if o.discount_value else None,
            start_date=o.start_date,
            end_date=o.end_date,
            is_active=o.is_active,
            first_seen_at=o.first_seen_at,
            last_seen_at=o.last_seen_at,
        )
        for o in offers
    ]


@router.get("/history")
async def get_offers_history(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    source_app: Optional[str] = Query(None, description="Filter by source app"),
    start_date: Optional[datetime] = Query(None, description="Start date filter"),
    end_date: Optional[datetime] = Query(None, description="End date filter"),
    db: Session = Depends(get_db),
) -> PaginatedResponse[OfferResponse]:
    """Get historical offers."""
    query = db.query(Offer).options(joinedload(Offer.product))

    if source_app:
        query = query.filter(Offer.source_app == source_app)
    if start_date:
        query = query.filter(Offer.first_seen_at >= start_date)
    if end_date:
        query = query.filter(Offer.first_seen_at <= end_date)

    total = query.count()

    offset = (page - 1) * per_page
    offers = (
        query
        .order_by(Offer.first_seen_at.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )

    items = [
        OfferResponse(
            id=o.id,
            source_app=o.source_app,
            external_id=o.external_id,
            product_id=o.product_id,
            product_name=o.product.name if o.product else None,
            title=o.title,
            title_ar=o.title_ar,
            description=o.description,
            description_ar=o.description_ar,
            discount_type=o.discount_type,
            discount_value=float(o.discount_value) if o.discount_value else None,
            start_date=o.start_date,
            end_date=o.end_date,
            is_active=o.is_active,
            first_seen_at=o.first_seen_at,
            last_seen_at=o.last_seen_at,
        )
        for o in offers
    ]

    meta = PaginationMeta.from_pagination(total, page, per_page)
    return PaginatedResponse(data=items, meta=meta)
