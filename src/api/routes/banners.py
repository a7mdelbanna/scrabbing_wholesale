"""Banners API routes."""
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.api.middleware.error_handler import NotFoundError
from src.api.schemas.common import PaginatedResponse, PaginationMeta
from src.models.database import Banner

router = APIRouter(prefix="/banners", tags=["Banners"])


class BannerResponse(BaseModel):
    """Banner response schema."""

    id: int = Field(..., description="Banner ID")
    source_app: str = Field(..., description="Source application")
    external_id: str = Field(..., description="External ID")
    title: Optional[str] = Field(None, description="Banner title")
    title_ar: Optional[str] = Field(None, description="Arabic title")
    image_url: str = Field(..., description="Banner image URL")
    link_type: Optional[str] = Field(None, description="Link type (product, category, offer, external)")
    link_target_id: Optional[str] = Field(None, description="Target ID")
    link_url: Optional[str] = Field(None, description="Full URL for external links")
    position: int = Field(default=0, description="Display position")
    is_active: bool = Field(default=True, description="Is banner active")
    start_date: Optional[datetime] = Field(None, description="Start date")
    end_date: Optional[datetime] = Field(None, description="End date")
    first_seen_at: Optional[datetime] = Field(None, description="First seen")
    last_seen_at: Optional[datetime] = Field(None, description="Last seen")

    class Config:
        from_attributes = True


def build_banner_response(banner: Banner) -> BannerResponse:
    """Build banner response from ORM model."""
    return BannerResponse(
        id=banner.id,
        source_app=banner.source_app,
        external_id=banner.external_id,
        title=banner.title,
        title_ar=banner.title_ar,
        image_url=banner.image_url,
        link_type=banner.link_type,
        link_target_id=banner.link_target_id,
        link_url=banner.link_url,
        position=banner.position,
        is_active=banner.is_active,
        start_date=banner.start_date,
        end_date=banner.end_date,
        first_seen_at=banner.first_seen_at,
        last_seen_at=banner.last_seen_at,
    )


@router.get("", response_model=PaginatedResponse[BannerResponse])
async def list_banners(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    source_app: Optional[str] = Query(None, description="Filter by source app"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    link_type: Optional[str] = Query(None, description="Filter by link type"),
    db: Session = Depends(get_db),
):
    """List banners with filters and pagination."""
    query = db.query(Banner)

    if source_app:
        query = query.filter(Banner.source_app == source_app)
    if is_active is not None:
        if is_active:
            now = datetime.utcnow()
            query = query.filter(
                Banner.is_active == True,
                or_(Banner.end_date.is_(None), Banner.end_date >= now)
            )
        else:
            query = query.filter(Banner.is_active == False)
    if link_type:
        query = query.filter(Banner.link_type == link_type)

    total = query.count()

    offset = (page - 1) * per_page
    banners = (
        query
        .order_by(Banner.position, Banner.created_at.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )

    items = [build_banner_response(b) for b in banners]
    meta = PaginationMeta.from_pagination(total, page, per_page)

    return PaginatedResponse(data=items, meta=meta)


@router.get("/stats")
async def get_banner_stats(
    db: Session = Depends(get_db),
):
    """Get banner statistics."""
    from sqlalchemy import func

    total = db.query(func.count(Banner.id)).scalar()
    active = db.query(func.count(Banner.id)).filter(Banner.is_active == True).scalar()

    by_app = dict(
        db.query(Banner.source_app, func.count(Banner.id))
        .group_by(Banner.source_app)
        .all()
    )

    by_type = dict(
        db.query(Banner.link_type, func.count(Banner.id))
        .filter(Banner.link_type.isnot(None))
        .group_by(Banner.link_type)
        .all()
    )

    return {
        "total_banners": total,
        "active_banners": active,
        "by_app": by_app,
        "by_link_type": by_type,
    }


@router.get("/by-app/{source_app}", response_model=List[BannerResponse])
async def get_banners_by_app(
    source_app: str,
    is_active: Optional[bool] = Query(True, description="Filter by active status"),
    db: Session = Depends(get_db),
):
    """Get banners for a specific app."""
    query = db.query(Banner).filter(Banner.source_app == source_app)

    if is_active is not None:
        if is_active:
            now = datetime.utcnow()
            query = query.filter(
                Banner.is_active == True,
                or_(Banner.end_date.is_(None), Banner.end_date >= now)
            )
        else:
            query = query.filter(Banner.is_active == False)

    banners = query.order_by(Banner.position).all()
    return [build_banner_response(b) for b in banners]


@router.get("/{banner_id}", response_model=BannerResponse)
async def get_banner(
    banner_id: int,
    db: Session = Depends(get_db),
):
    """Get banner details by ID."""
    banner = db.query(Banner).filter(Banner.id == banner_id).first()
    if not banner:
        raise NotFoundError("Banner", banner_id)

    return build_banner_response(banner)
