"""Product linking API routes for cross-app product matching."""
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.api.middleware.error_handler import NotFoundError, ValidationError
from src.api.schemas.common import PaginatedResponse, PaginationMeta, SuccessResponse
from src.models.database import ProductLink, Product
from src.services.linking_service import LinkingService

router = APIRouter(prefix="/product-links", tags=["Product Links"])


class ProductLinkCreate(BaseModel):
    """Create product link request."""

    product_a_id: int = Field(..., description="First product ID")
    product_b_id: int = Field(..., description="Second product ID")
    verified_by: Optional[str] = Field(None, description="Name of person creating the link")


class UnitLinkCreate(BaseModel):
    """Create unit-level product link request."""

    product_a_id: int = Field(..., description="First product ID")
    product_b_id: int = Field(..., description="Second product ID")
    unit_a_id: int = Field(..., description="Unit ID from first product")
    unit_b_id: int = Field(..., description="Unit ID from second product")
    verified_by: Optional[str] = Field(None, description="Name of person creating the link")


class ProductLinkResponse(BaseModel):
    """Product link response."""

    id: int
    product_a_id: int
    product_a_name: Optional[str] = None
    product_a_app: Optional[str] = None
    product_b_id: int
    product_b_name: Optional[str] = None
    product_b_app: Optional[str] = None
    # Unit-level link info
    unit_a_id: Optional[int] = None
    unit_a_name: Optional[str] = None
    unit_a_factor: Optional[int] = None
    unit_b_id: Optional[int] = None
    unit_b_name: Optional[str] = None
    unit_b_factor: Optional[int] = None
    link_type: str
    confidence_score: Optional[float] = None
    match_reason: Optional[str] = None
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None
    is_active: bool = True
    created_at: datetime

    class Config:
        from_attributes = True


class UnitInfo(BaseModel):
    """Unit information."""
    unit_id: int
    name: str
    name_ar: Optional[str] = None
    factor: int = 1
    barcode: Optional[str] = None
    price: Optional[float] = None
    price_per_base: Optional[float] = None
    is_available: bool = True


class UnitMatchResult(BaseModel):
    """Unit match result."""
    unit_id: int
    name: str
    name_ar: Optional[str] = None
    factor: int = 1
    barcode: Optional[str] = None
    price: Optional[float] = None
    price_per_base: Optional[float] = None
    is_available: bool = True
    score: float
    match_reasons: List[str]
    match_type: str


class UnitLinkSuggestion(BaseModel):
    """Unit link suggestion."""
    unit_a: UnitInfo
    unit_b: UnitInfo
    score: float
    match_reasons: List[str]
    match_type: str
    factor_warning: bool = False


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


class AutoLinkResponse(BaseModel):
    """Auto-link operation response."""

    links_created: int
    links_skipped: int
    products_processed: int
    errors: List[str] = []


def build_link_response(link: ProductLink, db: Session) -> ProductLinkResponse:
    """Build link response with product and unit details."""
    from src.models.database import ProductUnit

    product_a = db.query(Product).filter(Product.id == link.product_a_id).first()
    product_b = db.query(Product).filter(Product.id == link.product_b_id).first()

    # Get unit info if unit-level link
    unit_a = None
    unit_b = None
    if link.unit_a_id:
        unit_a = db.query(ProductUnit).filter(ProductUnit.id == link.unit_a_id).first()
    if link.unit_b_id:
        unit_b = db.query(ProductUnit).filter(ProductUnit.id == link.unit_b_id).first()

    return ProductLinkResponse(
        id=link.id,
        product_a_id=link.product_a_id,
        product_a_name=product_a.name if product_a else None,
        product_a_app=product_a.source_app if product_a else None,
        product_b_id=link.product_b_id,
        product_b_name=product_b.name if product_b else None,
        product_b_app=product_b.source_app if product_b else None,
        unit_a_id=link.unit_a_id,
        unit_a_name=unit_a.name if unit_a else None,
        unit_a_factor=unit_a.factor if unit_a else None,
        unit_b_id=link.unit_b_id,
        unit_b_name=unit_b.name if unit_b else None,
        unit_b_factor=unit_b.factor if unit_b else None,
        link_type=link.link_type,
        confidence_score=float(link.confidence_score) if link.confidence_score else None,
        match_reason=link.match_reason,
        verified_by=link.verified_by,
        verified_at=link.verified_at,
        is_active=link.is_active,
        created_at=link.created_at,
    )


@router.get("", response_model=PaginatedResponse[ProductLinkResponse])
async def list_product_links(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    link_type: Optional[str] = Query(None, description="Filter by link type (barcode, manual, suggested, verified)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    product_id: Optional[int] = Query(None, description="Filter by product ID"),
    db: Session = Depends(get_db),
):
    """List all product links with filters."""
    query = db.query(ProductLink)

    if link_type:
        query = query.filter(ProductLink.link_type == link_type)
    if is_active is not None:
        query = query.filter(ProductLink.is_active == is_active)
    if product_id:
        query = query.filter(
            (ProductLink.product_a_id == product_id) |
            (ProductLink.product_b_id == product_id)
        )

    total = query.count()

    offset = (page - 1) * per_page
    links = (
        query
        .order_by(ProductLink.created_at.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )

    items = [build_link_response(link, db) for link in links]
    meta = PaginationMeta.from_pagination(total, page, per_page)

    return PaginatedResponse(data=items, meta=meta)


@router.get("/stats")
async def get_link_stats(
    db: Session = Depends(get_db),
):
    """Get product link statistics."""
    total_links = db.query(func.count(ProductLink.id)).scalar()
    active_links = db.query(func.count(ProductLink.id)).filter(ProductLink.is_active == True).scalar()

    by_type = dict(
        db.query(ProductLink.link_type, func.count(ProductLink.id))
        .group_by(ProductLink.link_type)
        .all()
    )

    verified_count = db.query(func.count(ProductLink.id)).filter(
        ProductLink.verified_by.isnot(None)
    ).scalar()

    # Count unique products that are linked
    linked_products_a = db.query(func.count(func.distinct(ProductLink.product_a_id))).scalar()
    linked_products_b = db.query(func.count(func.distinct(ProductLink.product_b_id))).scalar()

    return {
        "total_links": total_links,
        "active_links": active_links,
        "by_type": by_type,
        "verified_count": verified_count,
        "unique_products_linked": linked_products_a + linked_products_b,
    }


@router.post("", response_model=ProductLinkResponse)
async def create_product_link(
    link_data: ProductLinkCreate,
    db: Session = Depends(get_db),
):
    """Create a manual product link."""
    service = LinkingService(db)

    try:
        link = service.create_manual_link(
            product_a_id=link_data.product_a_id,
            product_b_id=link_data.product_b_id,
            verified_by=link_data.verified_by,
        )
        return build_link_response(link, db)
    except ValueError as e:
        raise ValidationError(str(e))


@router.delete("/{link_id}")
async def delete_product_link(
    link_id: int,
    db: Session = Depends(get_db),
) -> SuccessResponse:
    """Delete a product link."""
    service = LinkingService(db)

    if not service.delete_link(link_id):
        raise NotFoundError("ProductLink", link_id)

    return SuccessResponse(message=f"Link {link_id} deleted successfully")


@router.post("/auto-link", response_model=AutoLinkResponse)
async def trigger_auto_linking(
    source_app: Optional[str] = Query(None, description="Source app to auto-link (optional)"),
    db: Session = Depends(get_db),
):
    """
    Trigger automatic product linking by barcode.

    This will find all products that share the same barcode across different apps
    and create links between them.
    """
    service = LinkingService(db)
    result = service.auto_link_by_barcode(source_app)

    return AutoLinkResponse(
        links_created=result["links_created"],
        links_skipped=result["links_skipped"],
        products_processed=result["products_processed"],
        errors=result["errors"],
    )


@router.get("/suggestions", response_model=List[ProductLinkSuggestion])
async def get_link_suggestions(
    min_similarity: float = Query(default=0.7, ge=0, le=1, description="Minimum similarity score"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum suggestions to return"),
    source_app: Optional[str] = Query(None, description="Filter by source app"),
    db: Session = Depends(get_db),
):
    """
    Get product link suggestions based on name similarity.

    This finds products without barcodes that might be the same product
    based on name similarity.
    """
    service = LinkingService(db)
    suggestions = service.get_link_suggestions(
        min_similarity=min_similarity,
        limit=limit,
        source_app=source_app,
    )

    return [ProductLinkSuggestion(**s) for s in suggestions]


@router.post("/{link_id}/verify", response_model=ProductLinkResponse)
async def verify_product_link(
    link_id: int,
    verified_by: str = Query(..., description="Name of verifier"),
    db: Session = Depends(get_db),
):
    """Verify a product link."""
    service = LinkingService(db)

    try:
        link = service.verify_link(link_id, verified_by)
        return build_link_response(link, db)
    except ValueError as e:
        raise NotFoundError("ProductLink", link_id)


@router.get("/search-in-app")
async def search_products_in_app(
    query: str = Query(..., min_length=2, description="Search query"),
    source_app: str = Query(..., description="App to search in"),
    limit: int = Query(default=10, ge=1, le=50, description="Max results"),
    db: Session = Depends(get_db),
):
    """
    Search for products by name in a specific app.

    Used for manual linking - search for a product in another app to link it.
    """
    service = LinkingService(db)
    results = service.search_products_in_app(query, source_app, limit)
    return results


@router.get("/smart-match/{product_id}")
async def get_smart_matches(
    product_id: int,
    target_app: str = Query(..., description="Target app to find matches in"),
    limit: int = Query(default=3, ge=1, le=10, description="Number of matches to return"),
    db: Session = Depends(get_db),
):
    """
    Find smart matches for a product in a target app.

    Uses multiple matching strategies:
    - Exact barcode match
    - SKU similarity
    - Token-based name matching
    - Brand + name matching
    - Arabic name matching

    Returns top matches with scores and match reasons.
    """
    service = LinkingService(db)
    matches = service.find_matches_for_product(product_id, target_app, limit)
    return matches


@router.get("/by-product/{product_id}")
async def get_links_for_product(
    product_id: int,
    db: Session = Depends(get_db),
) -> List[ProductLinkResponse]:
    """Get all links for a specific product."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise NotFoundError("Product", product_id)

    links = db.query(ProductLink).filter(
        (ProductLink.product_a_id == product_id) |
        (ProductLink.product_b_id == product_id),
        ProductLink.is_active == True,
    ).all()

    return [build_link_response(link, db) for link in links]


@router.get("/comparison/{product_id}")
async def get_comparison_by_links(
    product_id: int,
    db: Session = Depends(get_db),
):
    """
    Get price comparison for a product and all its linked products.

    This returns price information from all apps where this product
    (or linked products) exist.
    """
    service = LinkingService(db)
    result = service.get_comparison_by_link(product_id)

    if "error" in result:
        raise NotFoundError("Product", product_id)

    return result


@router.get("/{link_id}", response_model=ProductLinkResponse)
async def get_product_link(
    link_id: int,
    db: Session = Depends(get_db),
):
    """Get a specific product link by ID."""
    link = db.query(ProductLink).filter(ProductLink.id == link_id).first()
    if not link:
        raise NotFoundError("ProductLink", link_id)

    return build_link_response(link, db)


# ============= Unit-Level Linking Endpoints =============

@router.get("/units/{product_id}")
async def get_product_units(
    product_id: int,
    db: Session = Depends(get_db),
) -> List[UnitInfo]:
    """
    Get all units for a product with their prices.

    Returns units ordered by factor (smallest first).
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise NotFoundError("Product", product_id)

    service = LinkingService(db)
    units = service.get_product_units(product_id)

    return [UnitInfo(**u) for u in units]


@router.get("/unit-matches/{source_unit_id}/{target_product_id}")
async def get_unit_matches(
    source_unit_id: int,
    target_product_id: int,
    db: Session = Depends(get_db),
) -> List[UnitMatchResult]:
    """
    Find matching units in target product for a source unit.

    Uses multiple matching strategies:
    - Unit barcode match
    - Factor match
    - Unit name similarity
    - Normalized price similarity

    Returns list of matching units with scores.
    """
    service = LinkingService(db)
    matches = service.find_unit_matches(source_unit_id, target_product_id)

    return [UnitMatchResult(**m) for m in matches]


@router.get("/unit-suggestions/{product_a_id}/{product_b_id}")
async def get_unit_link_suggestions(
    product_a_id: int,
    product_b_id: int,
    db: Session = Depends(get_db),
) -> List[UnitLinkSuggestion]:
    """
    Get suggested unit-to-unit links between two products.

    Returns pairs of units that should be linked, sorted by confidence score.
    Includes warnings for factor mismatches.
    """
    # Validate products exist
    product_a = db.query(Product).filter(Product.id == product_a_id).first()
    product_b = db.query(Product).filter(Product.id == product_b_id).first()

    if not product_a:
        raise NotFoundError("Product", product_a_id)
    if not product_b:
        raise NotFoundError("Product", product_b_id)

    if product_a.source_app == product_b.source_app:
        raise ValidationError("Cannot get suggestions for products from the same app")

    service = LinkingService(db)
    suggestions = service.get_unit_link_suggestions(product_a_id, product_b_id)

    return [UnitLinkSuggestion(
        unit_a=UnitInfo(**s["unit_a"]),
        unit_b=UnitInfo(**s["unit_b"]),
        score=s["score"],
        match_reasons=s["match_reasons"],
        match_type=s["match_type"],
        factor_warning=s["factor_warning"],
    ) for s in suggestions]


@router.post("/unit-link", response_model=ProductLinkResponse)
async def create_unit_link(
    link_data: UnitLinkCreate,
    db: Session = Depends(get_db),
):
    """
    Create a unit-level link between two products.

    Links specific units from two products, enabling accurate price comparison.
    Validates that units belong to the specified products and have compatible factors.
    """
    service = LinkingService(db)

    try:
        link = service.create_unit_link(
            product_a_id=link_data.product_a_id,
            product_b_id=link_data.product_b_id,
            unit_a_id=link_data.unit_a_id,
            unit_b_id=link_data.unit_b_id,
            verified_by=link_data.verified_by,
        )
        return build_link_response(link, db)
    except ValueError as e:
        raise ValidationError(str(e))
