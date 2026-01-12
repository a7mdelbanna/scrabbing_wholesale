"""Common schemas used across API endpoints."""
from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field


# Generic type for paginated data
T = TypeVar("T")


class PaginationParams(BaseModel):
    """Pagination parameters."""

    page: int = Field(default=1, ge=1, description="Page number")
    per_page: int = Field(default=50, ge=1, le=100, description="Items per page")


class PaginationMeta(BaseModel):
    """Pagination metadata."""

    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Items per page")
    total_pages: int = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Has next page")
    has_prev: bool = Field(..., description="Has previous page")

    @classmethod
    def from_pagination(cls, total: int, page: int, per_page: int) -> "PaginationMeta":
        """Create pagination meta from parameters."""
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        return cls(
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response."""

    data: List[T] = Field(..., description="List of items")
    meta: PaginationMeta = Field(..., description="Pagination metadata")


class ErrorDetail(BaseModel):
    """Error detail."""

    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional details")


class ErrorResponse(BaseModel):
    """Error response."""

    error: ErrorDetail = Field(..., description="Error information")


class SuccessResponse(BaseModel):
    """Generic success response."""

    success: bool = Field(default=True)
    message: str = Field(..., description="Success message")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(default="healthy")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: str = Field(default="1.0.0")


class SortParams(BaseModel):
    """Sort parameters."""

    sort_by: Optional[str] = Field(None, description="Field to sort by")
    sort_order: str = Field(default="asc", pattern="^(asc|desc)$", description="Sort order")


class DateRangeParams(BaseModel):
    """Date range filter parameters."""

    start_date: Optional[datetime] = Field(None, description="Start date")
    end_date: Optional[datetime] = Field(None, description="End date")


class SourceAppFilter(BaseModel):
    """Source app filter."""

    source_app: Optional[str] = Field(
        None,
        description="Filter by source app (ben_soliman, tager_elsaada, el_rabie, gomla_shoaib)",
    )


class PriceInfo(BaseModel):
    """Price information."""

    price: float = Field(..., description="Current price")
    original_price: Optional[float] = Field(None, description="Original price before discount")
    discount_percentage: Optional[float] = Field(None, description="Discount percentage")
    currency: str = Field(default="EGP", description="Currency code")
    is_available: bool = Field(..., description="Availability status")
    recorded_at: Optional[datetime] = Field(None, description="When price was recorded")


class UnitInfo(BaseModel):
    """Product unit information."""

    id: int = Field(..., description="Unit ID")
    external_id: Optional[str] = Field(None, description="External unit ID")
    name: str = Field(..., description="Unit name")
    name_ar: Optional[str] = Field(None, description="Arabic unit name")
    factor: int = Field(default=1, description="Quantity factor from base unit")
    is_base_unit: bool = Field(default=False, description="Is this the base unit")
    barcode: Optional[str] = Field(None, description="Unit-specific barcode")
    current_price: Optional[PriceInfo] = Field(None, description="Current price for this unit")


class CategoryInfo(BaseModel):
    """Category information."""

    id: int = Field(..., description="Category ID")
    name: str = Field(..., description="Category name")
    name_ar: Optional[str] = Field(None, description="Arabic category name")
    image_url: Optional[str] = Field(None, description="Category image URL")


class BrandInfo(BaseModel):
    """Brand information."""

    id: int = Field(..., description="Brand ID")
    name: str = Field(..., description="Brand name")
    name_ar: Optional[str] = Field(None, description="Arabic brand name")
    image_url: Optional[str] = Field(None, description="Brand image URL")
