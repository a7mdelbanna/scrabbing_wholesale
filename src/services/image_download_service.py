"""Image download service for batch and single image downloads."""
import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session, joinedload

from src.models.database import Product, Category, Brand, ExportJob

logger = logging.getLogger(__name__)


class ImageDownloadService:
    """Service for downloading product images."""

    # Supported image extensions
    SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}

    # Default extension when unable to determine from URL
    DEFAULT_EXTENSION = '.jpg'

    # Download settings
    DOWNLOAD_DIR = "downloads/images"
    RATE_LIMIT_DELAY = 0.5  # seconds between downloads
    DOWNLOAD_TIMEOUT = 30.0  # seconds
    MAX_RETRIES = 3

    def __init__(self, db: Session):
        self.db = db
        self.download_dir = Path(self.DOWNLOAD_DIR)
        self.download_dir.mkdir(parents=True, exist_ok=True)

        # Track download statistics
        self._stats = {
            'total': 0,
            'downloaded': 0,
            'failed': 0,
            'skipped': 0,
        }

        # Image cache to avoid re-downloading same URLs
        self._url_cache: Dict[str, str] = {}

    def sanitize_filename(self, name: str, max_length: int = 200) -> str:
        """Sanitize a string for use as filename.

        Handles Arabic text by keeping safe characters.
        """
        if not name:
            return "unknown"

        # Remove or replace unsafe characters for filenames
        # Keep alphanumeric, Arabic characters, underscore, hyphen, dot
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(name))

        # Replace multiple underscores/spaces with single underscore
        safe_name = re.sub(r'[\s_]+', '_', safe_name)

        # Remove leading/trailing underscores
        safe_name = safe_name.strip('_')

        # Truncate if too long
        if len(safe_name) > max_length:
            safe_name = safe_name[:max_length]

        return safe_name or "unknown"

    def get_extension_from_url(self, url: str) -> str:
        """Extract file extension from URL."""
        if not url:
            return self.DEFAULT_EXTENSION

        parsed = urlparse(url)
        path = parsed.path.lower()

        for ext in self.SUPPORTED_EXTENSIONS:
            if path.endswith(ext):
                return ext

        # Check hints in URL
        url_lower = url.lower()
        if '.png' in url_lower or 'png' in parsed.query:
            return '.png'
        elif '.webp' in url_lower or 'webp' in parsed.query:
            return '.webp'
        elif '.gif' in url_lower or 'gif' in parsed.query:
            return '.gif'

        return self.DEFAULT_EXTENSION

    def generate_filename(
        self,
        product: Product,
        naming_convention: str,
        index: int = 0,
    ) -> str:
        """Generate filename based on naming convention.

        Args:
            product: Product model instance
            naming_convention: One of 'barcode', 'sku', 'barcode_source',
                             'external_id', or 'auto'
            index: Index for additional images (0 for main image)

        Returns:
            Filename without extension
        """
        suffix = f"_{index}" if index > 0 else ""

        if naming_convention == 'barcode' and product.barcode:
            return f"{self.sanitize_filename(product.barcode)}{suffix}"

        elif naming_convention == 'sku' and product.sku:
            return f"{self.sanitize_filename(product.sku)}{suffix}"

        elif naming_convention == 'barcode_source':
            identifier = product.barcode or product.sku or product.external_id
            return f"{self.sanitize_filename(identifier)}_{product.source_app}{suffix}"

        elif naming_convention == 'external_id':
            return f"{product.source_app}_{product.external_id}{suffix}"

        else:  # 'auto' - priority: barcode > sku > external_id
            if product.barcode:
                return f"{self.sanitize_filename(product.barcode)}{suffix}"
            elif product.sku:
                return f"{self.sanitize_filename(product.sku)}{suffix}"
            else:
                return f"{product.source_app}_{product.external_id}{suffix}"

    def get_folder_path(
        self,
        product: Product,
        folder_structure: str,
        base_path: Path,
    ) -> Path:
        """Determine folder path based on structure option.

        Args:
            product: Product model instance
            folder_structure: One of 'by_store', 'by_category', 'by_brand', 'flat'
            base_path: Base download directory

        Returns:
            Path object for the target folder
        """
        if folder_structure == 'flat':
            return base_path / "all"

        elif folder_structure == 'by_store':
            return base_path / product.source_app

        elif folder_structure == 'by_category':
            category_name = "uncategorized"
            if product.category:
                # Prefer English name, fallback to Arabic
                category_name = product.category.name or product.category.name_ar or "uncategorized"
            return base_path / product.source_app / self.sanitize_filename(category_name)

        elif folder_structure == 'by_brand':
            brand_name = "no_brand"
            if product.brand_rel:
                brand_name = product.brand_rel.name or product.brand_rel.name_ar or "no_brand"
            return base_path / product.source_app / self.sanitize_filename(brand_name)

        else:
            return base_path / product.source_app

    def _is_local_path(self, url: str) -> bool:
        """Check if URL is a local file path."""
        if not url:
            return False
        # Local paths start with / but not http
        return url.startswith('/static/') or url.startswith('/images/') or (
            url.startswith('/') and not url.startswith('//')
        )

    def _resolve_local_path(self, url: str) -> Optional[Path]:
        """Resolve a local URL path to filesystem path."""
        if not url:
            return None

        # Remove leading slash and resolve relative to project root
        relative_path = url.lstrip('/')

        # Try multiple base paths
        possible_paths = [
            Path(relative_path),  # Direct path
            Path('.') / relative_path,  # Relative to cwd
            Path(__file__).parent.parent.parent / relative_path,  # Relative to project root
        ]

        for path in possible_paths:
            if path.exists():
                return path

        return None

    async def download_single_image(
        self,
        url: str,
        target_path: Path,
        timeout: float = None,
    ) -> Tuple[bool, Optional[str]]:
        """Download a single image from URL or copy from local path.

        Args:
            url: Image URL to download or local path
            target_path: Local path to save the image
            timeout: Request timeout in seconds

        Returns:
            Tuple of (success, error_message)
        """
        if not url:
            return False, "No URL provided"

        # Handle local file paths (e.g., /static/images/products/...)
        if self._is_local_path(url):
            local_source = self._resolve_local_path(url)
            if local_source and local_source.exists():
                try:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(local_source, target_path)
                    return True, None
                except Exception as e:
                    return False, f"Failed to copy local file: {str(e)}"
            else:
                return False, f"Local file not found: {url}"

        # Check cache for remote URLs
        url_hash = hashlib.md5(url.encode()).hexdigest()
        if url_hash in self._url_cache:
            # Copy from cache location
            cached_path = self._url_cache[url_hash]
            if os.path.exists(cached_path):
                shutil.copy2(cached_path, target_path)
                return True, None

        timeout = timeout or self.DOWNLOAD_TIMEOUT

        for attempt in range(self.MAX_RETRIES):
            try:
                # Rate limiting delay
                await asyncio.sleep(self.RATE_LIMIT_DELAY)

                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.get(url, follow_redirects=True)

                    if response.status_code == 200:
                        # Ensure parent directory exists
                        target_path.parent.mkdir(parents=True, exist_ok=True)

                        # Write image data
                        with open(target_path, 'wb') as f:
                            f.write(response.content)

                        # Cache the URL
                        self._url_cache[url_hash] = str(target_path)

                        return True, None

                    elif response.status_code == 404:
                        return False, "Image not found (404)"

                    elif response.status_code == 429:
                        # Rate limited - wait and retry
                        retry_after = int(response.headers.get('Retry-After', 30))
                        await asyncio.sleep(retry_after)
                        continue

                    else:
                        return False, f"HTTP {response.status_code}"

            except httpx.TimeoutException:
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                return False, "Timeout"

            except httpx.NetworkError as e:
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return False, f"Network error: {str(e)}"

            except Exception as e:
                logger.error(f"Error downloading {url}: {e}")
                return False, str(e)

        return False, "Max retries exceeded"

    def get_products_for_download(
        self,
        source_app: Optional[str] = None,
        category_id: Optional[int] = None,
        brand_id: Optional[int] = None,
        product_ids: Optional[List[int]] = None,
        max_images: int = 1000,
    ) -> List[Product]:
        """Query products for image download with filters."""
        query = self.db.query(Product).options(
            joinedload(Product.category),
            joinedload(Product.brand_rel),
        ).filter(
            Product.image_url.isnot(None),
            Product.image_url != "",
        )

        if source_app:
            query = query.filter(Product.source_app == source_app)
        if category_id:
            query = query.filter(Product.category_id == category_id)
        if brand_id:
            query = query.filter(Product.brand_id == brand_id)
        if product_ids:
            query = query.filter(Product.id.in_(product_ids))

        return query.limit(max_images).all()

    async def process_batch_download(
        self,
        job_id: int,
        source_app: Optional[str] = None,
        category_id: Optional[int] = None,
        brand_id: Optional[int] = None,
        product_ids: Optional[List[int]] = None,
        folder_structure: str = "by_store",
        naming_convention: str = "auto",
        include_additional: bool = False,
        max_images: int = 1000,
    ) -> ExportJob:
        """Process batch image download and create ZIP file.

        This is the main method for batch downloads. It:
        1. Queries products based on filters
        2. Downloads images with rate limiting
        3. Creates a ZIP file with proper folder structure
        4. Updates job progress throughout
        """
        from src.services.export_service import ExportService
        export_service = ExportService(self.db)

        try:
            # Update job to processing
            export_service.update_export_job(job_id, "processing")

            # Get products
            products = self.get_products_for_download(
                source_app=source_app,
                category_id=category_id,
                brand_id=brand_id,
                product_ids=product_ids,
                max_images=max_images,
            )

            if not products:
                return export_service.update_export_job(
                    job_id=job_id,
                    status="completed",
                    records_count=0,
                    error_message="No products found matching criteria",
                )

            # Calculate total images
            total_images = len(products)
            if include_additional:
                for p in products:
                    if p.additional_images:
                        total_images += len(p.additional_images)

            self._stats = {
                'total': total_images,
                'downloaded': 0,
                'failed': 0,
                'skipped': 0,
            }

            # Create temporary directory for downloads
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            temp_dir = self.download_dir / f"temp_{job_id}_{timestamp}"
            temp_dir.mkdir(parents=True, exist_ok=True)

            # Download manifest to track files
            manifest = []
            failed_downloads = []

            try:
                for idx, product in enumerate(products):
                    # Log progress every 10 products
                    if idx % 10 == 0:
                        logger.info(f"Downloading image {idx+1}/{len(products)}")

                    # Determine folder and filename
                    folder = self.get_folder_path(product, folder_structure, temp_dir)
                    base_filename = self.generate_filename(product, naming_convention)
                    ext = self.get_extension_from_url(product.image_url)
                    filename = f"{base_filename}{ext}"
                    target_path = folder / filename

                    # Handle duplicates
                    counter = 1
                    while target_path.exists():
                        filename = f"{base_filename}_{counter}{ext}"
                        target_path = folder / filename
                        counter += 1

                    # Download main image
                    success, error = await self.download_single_image(
                        product.image_url,
                        target_path,
                    )

                    if success:
                        self._stats['downloaded'] += 1
                        manifest.append({
                            'product_id': product.id,
                            'source_app': product.source_app,
                            'barcode': product.barcode,
                            'sku': product.sku,
                            'filename': str(target_path.relative_to(temp_dir)),
                            'original_url': product.image_url,
                        })
                    else:
                        self._stats['failed'] += 1
                        failed_downloads.append({
                            'product_id': product.id,
                            'url': product.image_url,
                            'error': error,
                        })

                    # Download additional images if requested
                    if include_additional and product.additional_images:
                        for add_idx, add_url in enumerate(product.additional_images, 1):
                            add_filename = self.generate_filename(
                                product, naming_convention, index=add_idx
                            )
                            add_ext = self.get_extension_from_url(add_url)
                            add_target = folder / f"{add_filename}{add_ext}"

                            success, error = await self.download_single_image(
                                add_url,
                                add_target,
                            )

                            if success:
                                self._stats['downloaded'] += 1
                                manifest.append({
                                    'product_id': product.id,
                                    'filename': str(add_target.relative_to(temp_dir)),
                                    'original_url': add_url,
                                    'is_additional': True,
                                })
                            else:
                                self._stats['failed'] += 1

                # Create ZIP file
                zip_filename = f"images_{timestamp}.zip"
                zip_path = self.download_dir / zip_filename

                logger.info(f"Creating ZIP file: {zip_path}")

                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    # Add all downloaded images
                    for root, dirs, files in os.walk(temp_dir):
                        for file in files:
                            file_path = Path(root) / file
                            arcname = file_path.relative_to(temp_dir)
                            zf.write(file_path, arcname)

                    # Add manifest JSON
                    manifest_json = json.dumps(manifest, indent=2, ensure_ascii=False)
                    zf.writestr('manifest.json', manifest_json)

                    # Add failed downloads log if any
                    if failed_downloads:
                        failed_json = json.dumps(failed_downloads, indent=2, ensure_ascii=False)
                        zf.writestr('failed_downloads.json', failed_json)

                # Get ZIP file size
                file_size = os.path.getsize(zip_path)

                logger.info(f"Download complete: {self._stats['downloaded']} downloaded, {self._stats['failed']} failed")

                # Update job as completed
                return export_service.update_export_job(
                    job_id=job_id,
                    status="completed",
                    file_path=str(zip_path),
                    file_name=zip_filename,
                    file_size_bytes=file_size,
                    records_count=self._stats['downloaded'],
                )

            finally:
                # Cleanup temporary directory
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)

        except Exception as e:
            logger.error(f"Batch download failed: {e}", exc_info=True)
            return export_service.update_export_job(
                job_id=job_id,
                status="failed",
                error_message=str(e),
            )

    async def download_product_image(
        self,
        product_id: int,
        save_locally: bool = False,
    ) -> Dict[str, Any]:
        """Download a single product's image.

        Args:
            product_id: Product ID to download image for
            save_locally: Whether to save to static/images/products/

        Returns:
            Dict with download result
        """
        product = self.db.query(Product).options(
            joinedload(Product.category),
            joinedload(Product.brand_rel),
        ).filter(Product.id == product_id).first()

        if not product:
            return {
                'success': False,
                'error': 'Product not found',
            }

        if not product.image_url:
            return {
                'success': False,
                'error': 'Product has no image URL',
            }

        result = {
            'product_id': product.id,
            'source_app': product.source_app,
            'image_url': product.image_url,
            'barcode': product.barcode,
            'sku': product.sku,
        }

        if save_locally:
            # Save to static/images/products/
            static_dir = Path("static/images/products")
            static_dir.mkdir(parents=True, exist_ok=True)

            ext = self.get_extension_from_url(product.image_url)
            filename = f"{product.source_app}_{product.external_id}{ext}"
            target_path = static_dir / filename

            success, error = await self.download_single_image(
                product.image_url,
                target_path,
            )

            result['downloaded'] = success
            result['local_path'] = str(target_path) if success else None
            result['filename'] = filename
            if error:
                result['error'] = error
        else:
            # Just return the URL info
            ext = self.get_extension_from_url(product.image_url)
            filename = self.generate_filename(product, 'auto')
            result['filename'] = f"{filename}{ext}"
            result['downloaded'] = False

        return result

    def get_image_info_list(
        self,
        source_app: Optional[str] = None,
        category_id: Optional[int] = None,
        brand_id: Optional[int] = None,
        max_images: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get list of image info without downloading.

        Useful for previewing what would be downloaded.
        """
        products = self.get_products_for_download(
            source_app=source_app,
            category_id=category_id,
            brand_id=brand_id,
            max_images=max_images,
        )

        images = []
        for product in products:
            ext = self.get_extension_from_url(product.image_url)
            filename = self.generate_filename(product, 'auto')

            images.append({
                'product_id': product.id,
                'source_app': product.source_app,
                'image_url': product.image_url,
                'filename': f"{filename}{ext}",
                'barcode': product.barcode,
                'sku': product.sku,
                'category_name': product.category.name if product.category else None,
                'brand_name': product.brand_rel.name if product.brand_rel else None,
            })

        return images
