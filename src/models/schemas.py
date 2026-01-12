"""Pydantic schemas for data validation."""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field, field_validator

from .enums import SourceApp, Currency, UnitType, StockStatus


# ============== API Response Schemas ==============
# These schemas represent raw API responses - adjust after API discovery

class ProductAPIResponse(BaseModel):
    """Schema for raw product API response.

    NOTE: This is a placeholder. Update fields after API discovery.
    """
    id: str
    name: str
    name_ar: Optional[str] = None
    description: Optional[str] = None
    description_ar: Optional[str] = None
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    brand: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    image_url: Optional[str] = None
    images: Optional[List[str]] = None
    price: Decimal
    original_price: Optional[Decimal] = None
    discount_percentage: Optional[Decimal] = None
    unit: Optional[str] = None
    min_order_quantity: Optional[int] = 1
    stock_status: Optional[str] = None
    is_available: bool = True


class CategoryAPIResponse(BaseModel):
    """Schema for raw category API response."""
    id: str
    name: str
    name_ar: Optional[str] = None
    parent_id: Optional[str] = None
    image_url: Optional[str] = None
    sort_order: Optional[int] = None


class OfferAPIResponse(BaseModel):
    """Schema for raw offer API response."""
    id: str
    title: str
    title_ar: Optional[str] = None
    description: Optional[str] = None
    product_id: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[Decimal] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


# ============== Domain Models ==============
# These schemas are used for creating database records

class CategoryCreate(BaseModel):
    """Schema for creating a category."""
    source_app: SourceApp
    external_id: str
    name: str
    name_ar: Optional[str] = None
    parent_external_id: Optional[str] = None
    image_url: Optional[str] = None
    sort_order: Optional[int] = None


class ProductCreate(BaseModel):
    """Schema for creating a product."""
    source_app: SourceApp
    external_id: str
    name: str
    name_ar: Optional[str] = None
    description: Optional[str] = None
    description_ar: Optional[str] = None
    category_external_id: Optional[str] = None
    category_name: Optional[str] = None
    category_name_ar: Optional[str] = None
    brand: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    image_url: Optional[str] = None
    additional_images: Optional[List[str]] = None
    unit_type: UnitType = UnitType.PIECE
    unit_value: Optional[Decimal] = None
    min_order_quantity: int = 1
    extra_data: Optional[Dict[str, Any]] = None


class PriceRecordCreate(BaseModel):
    """Schema for creating a price record."""
    product_id: int
    source_app: SourceApp
    price: Decimal
    original_price: Optional[Decimal] = None
    discount_percentage: Optional[Decimal] = None
    currency: Currency = Currency.EGP
    is_available: bool = True
    stock_status: Optional[StockStatus] = None

    @field_validator("price", "original_price", "discount_percentage", mode="before")
    @classmethod
    def convert_to_decimal(cls, v):
        if v is not None:
            return Decimal(str(v))
        return v


class OfferCreate(BaseModel):
    """Schema for creating an offer."""
    source_app: SourceApp
    external_id: str
    product_id: Optional[int] = None
    title: str
    title_ar: Optional[str] = None
    description: Optional[str] = None
    description_ar: Optional[str] = None
    discount_type: str  # percentage, fixed, buy_x_get_y
    discount_value: Decimal
    min_quantity: Optional[int] = None
    max_quantity: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_active: bool = True
    extra_data: Optional[Dict[str, Any]] = None


# ============== Response/Report Models ==============

class PriceHistoryItem(BaseModel):
    """Single price history entry."""
    price: Decimal
    original_price: Optional[Decimal]
    discount_percentage: Optional[Decimal]
    recorded_at: datetime
    is_available: bool


class ProductWithPriceHistory(BaseModel):
    """Product with its price history."""
    id: int
    source_app: SourceApp
    external_id: str
    name: str
    name_ar: Optional[str]
    current_price: Decimal
    price_history: List[PriceHistoryItem]
    category_name: Optional[str]
    brand: Optional[str]


class PriceComparisonItem(BaseModel):
    """Price comparison between apps."""
    product_name: str
    product_name_ar: Optional[str]
    barcode: Optional[str]
    tager_elsaada_price: Optional[Decimal]
    ben_soliman_price: Optional[Decimal]
    price_difference: Optional[Decimal]
    cheaper_source: Optional[SourceApp]


class ScrapeJobSummary(BaseModel):
    """Summary of a scrape job."""
    id: int
    source_app: SourceApp
    job_type: str
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    products_scraped: int
    products_updated: int
    products_new: int
    errors_count: int
    duration_seconds: Optional[float] = None

    class Config:
        from_attributes = True
