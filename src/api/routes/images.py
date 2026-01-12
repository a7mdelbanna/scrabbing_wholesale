"""Image download API routes."""
import os
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.api.middleware.error_handler import NotFoundError, ValidationError
from src.api.schemas.images import (
    ImageDownloadRequest,
    ImageDownloadJobResponse,
    SingleImageResponse,
    ImageInfo,
    BulkSaveResponse,
    FolderStructure,
    NamingConvention,
)
from src.models.database import ExportJob, Product
from src.services.image_download_service import ImageDownloadService
from src.services.export_service import ExportService

router = APIRouter(prefix="/images", tags=["Images"])


def build_job_response(job: ExportJob, base_url: str = "") -> ImageDownloadJobResponse:
    """Build image download job response from ORM model."""
    download_url = None
    if job.status == "completed" and job.file_path:
        download_url = f"/api/v1/images/download/{job.id}/file"

    # Parse parameters for additional info
    params = job.parameters or {}

    return ImageDownloadJobResponse(
        id=job.id,
        status=job.status,
        progress_percent=job.progress_percent or 0,
        total_images=params.get('max_images'),
        downloaded_images=job.records_count,
        failed_images=params.get('failed_images'),
        file_name=job.file_name,
        file_size_bytes=job.file_size_bytes,
        download_url=download_url,
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
        expires_at=job.expires_at,
        created_at=job.created_at,
    )


async def run_batch_download(job_id: int, request: ImageDownloadRequest, db: Session):
    """Background task to run batch image download."""
    service = ImageDownloadService(db)
    await service.process_batch_download(
        job_id=job_id,
        source_app=request.source_app,
        category_id=request.category_id,
        brand_id=request.brand_id,
        product_ids=request.product_ids,
        folder_structure=request.folder_structure.value,
        naming_convention=request.naming_convention.value,
        include_additional=request.include_additional_images,
        max_images=request.max_images,
    )


@router.post("/download", response_model=ImageDownloadJobResponse)
async def start_image_download(
    request: ImageDownloadRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Start a batch image download job.

    Creates a background job to download images based on the provided filters.
    Returns immediately with a job ID that can be polled for status.

    ## Filters (all optional, combine as needed):
    - **source_app**: Filter by store (ben_soliman, tager_elsaada, el_rabie, gomla_shoaib)
    - **category_id**: Filter by category
    - **brand_id**: Filter by brand
    - **product_ids**: Specific product IDs (max 100)

    ## Folder Structure Options:
    - **by_store**: `{source_app}/{filename}`
    - **by_category**: `{source_app}/{category_name}/{filename}`
    - **by_brand**: `{source_app}/{brand_name}/{filename}`
    - **flat**: `all/{filename}`

    ## Naming Convention Options:
    - **auto**: Priority: barcode > sku > external_id (recommended)
    - **barcode**: `{barcode}.{ext}`
    - **sku**: `{sku}.{ext}`
    - **barcode_source**: `{barcode}_{source_app}.{ext}`
    - **external_id**: `{source_app}_{external_id}.{ext}`
    """
    # Validate product_ids count
    if request.product_ids and len(request.product_ids) > 100:
        raise ValidationError("Maximum 100 product IDs allowed per request")

    export_service = ExportService(db)

    # Create job record
    job = export_service.create_export_job(
        job_type="images_zip",
        parameters=request.model_dump(),
    )

    # Start background download
    background_tasks.add_task(run_batch_download, job.id, request, db)

    return build_job_response(job)


@router.get("/download/{job_id}", response_model=ImageDownloadJobResponse)
async def get_download_status(
    job_id: int,
    db: Session = Depends(get_db),
):
    """
    Get the status of an image download job.

    Poll this endpoint to check progress and get the download URL when complete.
    """
    export_service = ExportService(db)
    job = export_service.get_export_job(job_id)

    if not job:
        raise NotFoundError("ImageDownloadJob", job_id)

    if job.job_type != "images_zip":
        raise NotFoundError("ImageDownloadJob", job_id)

    return build_job_response(job)


@router.get("/download/{job_id}/file")
async def download_images_zip(
    job_id: int,
    db: Session = Depends(get_db),
):
    """
    Download the completed ZIP file for an image download job.

    Only available after job status is 'completed'.
    """
    export_service = ExportService(db)
    job = export_service.get_export_job(job_id)

    if not job:
        raise NotFoundError("ImageDownloadJob", job_id)

    if job.job_type != "images_zip":
        raise NotFoundError("ImageDownloadJob", job_id)

    if job.status != "completed":
        raise ValidationError(f"Download not ready. Job status: {job.status}")

    if not job.file_path or not os.path.exists(job.file_path):
        raise ValidationError("Download file not found or expired")

    return FileResponse(
        path=job.file_path,
        filename=job.file_name or f"images_{job_id}.zip",
        media_type="application/zip",
    )


@router.get("/products/{product_id}/download", response_model=SingleImageResponse)
async def download_product_image(
    product_id: int,
    save_locally: bool = Query(
        default=False,
        description="Save to static/images/products/"
    ),
    db: Session = Depends(get_db),
):
    """
    Download a single product's image.

    - Without `save_locally`: Returns image info and URL
    - With `save_locally=true`: Downloads and saves to server, returns local path
    """
    service = ImageDownloadService(db)
    result = await service.download_product_image(product_id, save_locally)

    if result.get('error') == 'Product not found':
        raise NotFoundError("Product", product_id)

    return SingleImageResponse(
        product_id=result.get('product_id'),
        source_app=result.get('source_app', ''),
        image_url=result.get('image_url', ''),
        local_path=result.get('local_path'),
        filename=result.get('filename', ''),
        downloaded=result.get('downloaded', False),
        error=result.get('error'),
        barcode=result.get('barcode'),
        sku=result.get('sku'),
    )


@router.get("/products/{product_id}/serve")
async def serve_product_image(
    product_id: int,
    db: Session = Depends(get_db),
):
    """
    Serve a product image directly (proxy download).

    Downloads the image on-the-fly and streams it to the client.
    Useful for displaying images without exposing source URLs.
    """
    import httpx

    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise NotFoundError("Product", product_id)

    if not product.image_url:
        raise ValidationError("Product has no image")

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(product.image_url, follow_redirects=True)

            if response.status_code != 200:
                raise ValidationError(f"Failed to fetch image: HTTP {response.status_code}")

            # Determine content type
            content_type = response.headers.get('content-type', 'image/jpeg')

            # Generate filename
            service = ImageDownloadService(db)
            ext = service.get_extension_from_url(product.image_url)
            filename = f"{product.source_app}_{product.external_id}{ext}"

            return StreamingResponse(
                iter([response.content]),
                media_type=content_type,
                headers={
                    "Content-Disposition": f"attachment; filename={filename}",
                },
            )
        except httpx.TimeoutException:
            raise ValidationError("Image download timed out")
        except httpx.NetworkError as e:
            raise ValidationError(f"Network error: {str(e)}")


@router.post("/bulk-save", response_model=BulkSaveResponse)
async def bulk_save_to_static(
    source_app: Optional[str] = Query(None, description="Filter by source app"),
    category_id: Optional[int] = Query(None, description="Filter by category"),
    brand_id: Optional[int] = Query(None, description="Filter by brand"),
    max_images: int = Query(default=100, ge=1, le=1000, description="Maximum images"),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    """
    Bulk save images to static/images/products/ directory.

    This saves images directly to the server's static directory
    using the standard naming: {source_app}_{external_id}.{ext}

    Returns the count of images queued for download.
    """
    service = ImageDownloadService(db)
    products = service.get_products_for_download(
        source_app=source_app,
        category_id=category_id,
        brand_id=brand_id,
        max_images=max_images,
    )

    if not products:
        return BulkSaveResponse(
            queued=0,
            message="No products found matching criteria"
        )

    # Queue downloads in background
    async def save_all():
        saved = 0
        for product in products:
            result = await service.download_product_image(product.id, save_locally=True)
            if result.get('downloaded'):
                saved += 1
        return saved

    if background_tasks:
        background_tasks.add_task(save_all)
        return BulkSaveResponse(
            queued=len(products),
            message=f"Queued {len(products)} images for download to static directory"
        )
    else:
        # Run synchronously for small batches
        import asyncio
        saved = await save_all()
        return BulkSaveResponse(
            queued=len(products),
            saved=saved,
            message=f"Saved {saved}/{len(products)} images to static directory"
        )


@router.get("/list", response_model=List[ImageInfo])
async def list_images(
    source_app: Optional[str] = Query(None, description="Filter by source app"),
    category_id: Optional[int] = Query(None, description="Filter by category"),
    brand_id: Optional[int] = Query(None, description="Filter by brand"),
    max_images: int = Query(default=100, ge=1, le=1000, description="Maximum images to list"),
    db: Session = Depends(get_db),
):
    """
    List images available for download without actually downloading.

    Useful for previewing what would be included in a batch download.
    """
    service = ImageDownloadService(db)
    images = service.get_image_info_list(
        source_app=source_app,
        category_id=category_id,
        brand_id=brand_id,
        max_images=max_images,
    )

    return [
        ImageInfo(
            product_id=img['product_id'],
            source_app=img['source_app'],
            image_url=img['image_url'],
            filename=img['filename'],
            barcode=img['barcode'],
            sku=img['sku'],
            category_name=img['category_name'],
            brand_name=img['brand_name'],
        )
        for img in images
    ]
