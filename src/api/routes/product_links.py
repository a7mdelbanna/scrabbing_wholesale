"""Product linking API routes for cross-app product matching."""
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.api.schemas.common import PaginatedResponse, PaginationMeta, SuccessResponse

router = APIRouter(prefix="/product-links", tags=["Product Links"])


class ProductLinkCreate(BaseModel):
    """Create product link request."""

    product_a_id: int = Field(..., description="First product ID")
    product_b_id: int = Field(..., description="Second product ID")
    link_type: str = Field(default="manual", description="Link type (barcode, manual, suggested)")


class ProductLinkResponse(BaseModel):
    """Product link response."""

    id: int
    product_a_id: int
    product_b_id: int
    link_type: str
    confidence_score: Optional[float] = None
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None
    created_at: datetime


class ProductLinkSuggestion(BaseModel):
    """Product link suggestion."""

    product_a_id: int
    product_a_name: str
    product_a_app: str
    product_b_id: int
    product_b_name: str
    product_b_app: str
    similarity_score: float
    match_reason: str


@router.get("")
async def list_product_links(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    link_type: Optional[str] = Query(None, description="Filter by link type"),
    db: Session = Depends(get_db),
) -> PaginatedResponse[ProductLinkResponse]:
    """List all product links."""
    # TODO: Implement when ProductLink model is added in Phase 2
    return PaginatedResponse(
        data=[],
        meta=PaginationMeta.from_pagination(0, page, per_page),
    )


@router.post("")
async def create_product_link(
    link_data: ProductLinkCreate,
    db: Session = Depends(get_db),
) -> ProductLinkResponse:
    """Create a manual product link."""
    # TODO: Implement when ProductLink model is added in Phase 2
    return ProductLinkResponse(
        id=0,
        product_a_id=link_data.product_a_id,
        product_b_id=link_data.product_b_id,
        link_type=link_data.link_type,
        created_at=datetime.utcnow(),
    )


@router.delete("/{link_id}")
async def delete_product_link(
    link_id: int,
    db: Session = Depends(get_db),
) -> SuccessResponse:
    """Delete a product link."""
    # TODO: Implement when ProductLink model is added in Phase 2
    return SuccessResponse(message=f"Link {link_id} deleted")


@router.post("/auto-link")
async def trigger_auto_linking(
    source_app: Optional[str] = Query(None, description="Source app to auto-link"),
    db: Session = Depends(get_db),
) -> SuccessResponse:
    """Trigger automatic product linking by barcode."""
    # TODO: Implement auto-linking logic in Phase 2
    return SuccessResponse(message="Auto-linking job started")


@router.get("/suggestions")
async def get_link_suggestions(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    min_similarity: float = Query(default=0.8, ge=0, le=1, description="Minimum similarity score"),
    db: Session = Depends(get_db),
) -> PaginatedResponse[ProductLinkSuggestion]:
    """Get product link suggestions based on name similarity."""
    # TODO: Implement similarity matching in Phase 2
    return PaginatedResponse(
        data=[],
        meta=PaginationMeta.from_pagination(0, page, per_page),
    )


@router.post("/{link_id}/verify")
async def verify_product_link(
    link_id: int,
    verified_by: str = Query(..., description="Name of verifier"),
    db: Session = Depends(get_db),
) -> ProductLinkResponse:
    """Verify a product link."""
    # TODO: Implement when ProductLink model is added in Phase 2
    return ProductLinkResponse(
        id=link_id,
        product_a_id=0,
        product_b_id=0,
        link_type="verified",
        verified_by=verified_by,
        verified_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
    )
