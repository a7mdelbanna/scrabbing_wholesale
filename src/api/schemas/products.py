"""Product-related schemas."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from src.api.schemas.common import (
    PriceInfo,
    UnitInfo,
    CategoryInfo,
    BrandInfo,
    PaginationParams,
    SourceAppFilter,
)


class ProductBase(BaseModel):
    """Base product fields."""

    name: str = Field(..., description="Product name")
    name_ar: Optional[str] = Field(None, description="Arabic product name")
    description: Optional[str] = Field(None, description="Product description")
    description_ar: Optional[str] = Field(None, description="Arabic description")
    sku: Optional[str] = Field(None, description="SKU code")
    barcode: Optional[str] = Field(None, description="Barcode for cross-app matching")
    image_url: Optional[str] = Field(None, description="Main product image URL")
    additional_images: Optional[List[str]] = Field(None, description="Additional images")


class ProductSummary(BaseModel):
    """Product summary for list views."""

    id: int = Field(..., description="Product ID")
    source_app: str = Field(..., description="Source application")
    external_id: str = Field(..., description="External ID in source app")
    name: str = Field(..., description="Product name")
    name_ar: Optional[str] = Field(None, description="Arabic product name")
    sku: Optional[str] = Field(None, description="SKU code")
    barcode: Optional[str] = Field(None, description="Barcode")
    image_url: Optional[str] = Field(None, description="Product image URL")
    category: Optional[CategoryInfo] = Field(None, description="Product category")
    brand: Optional[BrandInfo] = Field(None, description="Product brand")
    current_price: Optional[PriceInfo] = Field(None, description="Current price info")
    units_count: int = Field(default=0, description="Number of available units")
    is_active: bool = Field(..., description="Is product active")
    last_seen_at: Optional[datetime] = Field(None, description="Last seen timestamp")

    class Config:
        from_attributes = True


class ProductDetail(ProductSummary):
    """Detailed product information."""

    description: Optional[str] = Field(None, description="Product description")
    description_ar: Optional[str] = Field(None, description="Arabic description")
    additional_images: Optional[List[str]] = Field(None, description="Additional images")
    unit_type: Optional[str] = Field(None, description="Base unit type")
    unit_value: Optional[float] = Field(None, description="Base unit value")
    min_order_quantity: int = Field(default=1, description="Minimum order quantity")
    units: List[UnitInfo] = Field(default_factory=list, description="Available units")
    first_seen_at: Optional[datetime] = Field(None, description="First seen timestamp")
    created_at: Optional[datetime] = Field(None, description="Created timestamp")
    updated_at: Optional[datetime] = Field(None, description="Updated timestamp")

    class Config:
        from_attributes = True


class ProductListParams(PaginationParams, SourceAppFilter):
    """Parameters for listing products."""

    category_id: Optional[int] = Field(None, description="Filter by category ID")
    brand_id: Optional[int] = Field(None, description="Filter by brand ID")
    search: Optional[str] = Field(None, description="Search in name")
    barcode: Optional[str] = Field(None, description="Filter by barcode")
    sku: Optional[str] = Field(None, description="Filter by SKU")
    is_active: Optional[bool] = Field(None, description="Filter by active status")
    has_price: Optional[bool] = Field(None, description="Filter products with prices")
    min_price: Optional[float] = Field(None, description="Minimum price filter")
    max_price: Optional[float] = Field(None, description="Maximum price filter")
    sort_by: str = Field(default="name", description="Sort field")
    sort_order: str = Field(default="asc", pattern="^(asc|desc)$", description="Sort order")


class ProductSearchParams(BaseModel):
    """Parameters for product search."""

    query: str = Field(..., min_length=2, description="Search query")
    source_app: Optional[str] = Field(None, description="Filter by source app")
    limit: int = Field(default=20, ge=1, le=100, description="Maximum results")


class PriceHistoryParams(PaginationParams):
    """Parameters for price history."""

    start_date: Optional[datetime] = Field(None, description="Start date filter")
    end_date: Optional[datetime] = Field(None, description="End date filter")
    unit_id: Optional[int] = Field(None, description="Filter by unit ID")


class PriceHistoryItem(BaseModel):
    """Price history item."""

    id: int = Field(..., description="Price record ID")
    price: float = Field(..., description="Price")
    original_price: Optional[float] = Field(None, description="Original price")
    discount_percentage: Optional[float] = Field(None, description="Discount percentage")
    currency: str = Field(default="EGP", description="Currency")
    is_available: bool = Field(..., description="Availability status")
    unit_id: Optional[int] = Field(None, description="Unit ID if unit-specific")
    unit_name: Optional[str] = Field(None, description="Unit name")
    recorded_at: datetime = Field(..., description="Recording timestamp")

    class Config:
        from_attributes = True


class ProductUpdate(BaseModel):
    """Product update schema."""

    name: Optional[str] = Field(None, description="Product name")
    name_ar: Optional[str] = Field(None, description="Arabic product name")
    description: Optional[str] = Field(None, description="Product description")
    description_ar: Optional[str] = Field(None, description="Arabic description")
    barcode: Optional[str] = Field(None, description="Barcode")
    is_active: Optional[bool] = Field(None, description="Is product active")
