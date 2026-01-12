"""Banners API routes."""
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.api.schemas.common import PaginatedResponse, PaginationMeta

router = APIRouter(prefix="/banners", tags=["Banners"])


class BannerResponse(BaseModel):
    """Banner response schema."""

    id: int = Field(..., description="Banner ID")
    source_app: str = Field(..., description="Source application")
    external_id: str = Field(..., description="External ID")
    title: Optional[str] = Field(None, description="Banner title")
    image_url: str = Field(..., description="Banner image URL")
    link_type: Optional[str] = Field(None, description="Link type (product, category, offer, external)")
    link_target_id: Optional[str] = Field(None, description="Target ID")
    position: int = Field(default=0, description="Display position")
    is_active: bool = Field(default=True, description="Is banner active")
    start_date: Optional[datetime] = Field(None, description="Start date")
    end_date: Optional[datetime] = Field(None, description="End date")


@router.get("", response_model=PaginatedResponse[BannerResponse])
async def list_banners(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    source_app: Optional[str] = Query(None, description="Filter by source app"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: Session = Depends(get_db),
):
    """List banners with filters and pagination."""
    # TODO: Implement when Banner model is added in Phase 3
    return PaginatedResponse(
        data=[],
        meta=PaginationMeta.from_pagination(0, page, per_page),
    )


@router.get("/{banner_id}", response_model=BannerResponse)
async def get_banner(
    banner_id: int,
    db: Session = Depends(get_db),
):
    """Get banner details by ID."""
    # TODO: Implement when Banner model is added in Phase 3
    from src.api.middleware.error_handler import NotFoundError
    raise NotFoundError("Banner", banner_id)


@router.get("/by-app/{source_app}")
async def get_banners_by_app(
    source_app: str,
    is_active: Optional[bool] = Query(True, description="Filter by active status"),
    db: Session = Depends(get_db),
) -> List[BannerResponse]:
    """Get banners for a specific app."""
    # TODO: Implement when Banner model is added in Phase 3
    return []
