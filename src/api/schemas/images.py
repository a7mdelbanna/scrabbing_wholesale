"""Image download schemas."""
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field


class FolderStructure(str, Enum):
    """Folder organization options for downloaded images."""
    BY_STORE = "by_store"           # downloads/images/{source_app}/
    BY_CATEGORY = "by_category"     # downloads/images/{source_app}/{category_name}/
    BY_BRAND = "by_brand"           # downloads/images/{source_app}/{brand_name}/
    FLAT = "flat"                   # downloads/images/all/


class NamingConvention(str, Enum):
    """File naming options for downloaded images."""
    AUTO = "auto"                   # Priority: barcode > sku > external_id
    BARCODE = "barcode"             # {barcode}.{ext}
    SKU = "sku"                     # {sku}.{ext}
    BARCODE_SOURCE = "barcode_source"  # {barcode}_{source_app}.{ext}
    EXTERNAL_ID = "external_id"     # {source_app}_{external_id}.{ext}


class ImageDownloadRequest(BaseModel):
    """Batch image download request."""

    source_app: Optional[str] = Field(
        None,
        description="Filter by source app (ben_soliman, tager_elsaada, el_rabie, gomla_shoaib)"
    )
    category_id: Optional[int] = Field(
        None,
        description="Filter by category ID"
    )
    brand_id: Optional[int] = Field(
        None,
        description="Filter by brand ID"
    )
    product_ids: Optional[List[int]] = Field(
        None,
        description="Specific product IDs to download (max 100)"
    )
    folder_structure: FolderStructure = Field(
        default=FolderStructure.BY_STORE,
        description="How to organize downloaded images in folders"
    )
    naming_convention: NamingConvention = Field(
        default=NamingConvention.AUTO,
        description="How to name downloaded files"
    )
    include_additional_images: bool = Field(
        default=False,
        description="Include additional product images (not just main image)"
    )
    max_images: int = Field(
        default=1000,
        ge=1,
        le=10000,
        description="Maximum number of images to download"
    )


class ImageDownloadJobResponse(BaseModel):
    """Image download job status response."""

    id: int = Field(..., description="Job ID")
    status: str = Field(..., description="Job status (pending, processing, completed, failed)")
    progress_percent: int = Field(default=0, description="Download progress percentage")
    total_images: Optional[int] = Field(None, description="Total images to download")
    downloaded_images: Optional[int] = Field(None, description="Images downloaded so far")
    failed_images: Optional[int] = Field(None, description="Failed image downloads")
    file_name: Optional[str] = Field(None, description="Output ZIP filename")
    file_size_bytes: Optional[int] = Field(None, description="ZIP file size in bytes")
    download_url: Optional[str] = Field(None, description="URL to download the ZIP file")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    started_at: Optional[datetime] = Field(None, description="Job start time")
    completed_at: Optional[datetime] = Field(None, description="Job completion time")
    expires_at: Optional[datetime] = Field(None, description="When download link expires")
    created_at: datetime = Field(..., description="Job creation time")

    class Config:
        from_attributes = True


class SingleImageResponse(BaseModel):
    """Single image download/info response."""

    product_id: int = Field(..., description="Product ID")
    source_app: str = Field(..., description="Source application")
    image_url: str = Field(..., description="Original image URL")
    local_path: Optional[str] = Field(None, description="Local file path if saved")
    filename: str = Field(..., description="Generated filename")
    downloaded: bool = Field(default=False, description="Whether image was downloaded")
    error: Optional[str] = Field(None, description="Error message if download failed")
    barcode: Optional[str] = Field(None, description="Product barcode")
    sku: Optional[str] = Field(None, description="Product SKU")


class ImageInfo(BaseModel):
    """Image information for listing."""

    product_id: int
    source_app: str
    image_url: str
    filename: str
    barcode: Optional[str] = None
    sku: Optional[str] = None
    category_name: Optional[str] = None
    brand_name: Optional[str] = None


class BulkSaveResponse(BaseModel):
    """Response for bulk save to static directory."""

    queued: int = Field(..., description="Number of images queued for download")
    saved: Optional[int] = Field(None, description="Number of images saved (if synchronous)")
    message: str = Field(..., description="Status message")
