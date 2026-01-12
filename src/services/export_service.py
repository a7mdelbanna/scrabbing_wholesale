"""Export service for generating data exports."""
import csv
import io
import os
import zipfile
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from src.models.database import Product, PriceRecord, Category, Brand, ProductLink, ExportJob


class ExportService:
    """Service for generating data exports."""

    EXPORT_DIR = "exports"

    def __init__(self, db: Session):
        self.db = db
        # Ensure export directory exists
        os.makedirs(self.EXPORT_DIR, exist_ok=True)

    def export_products_csv(
        self,
        source_app: Optional[str] = None,
        category_id: Optional[int] = None,
        brand_id: Optional[int] = None,
        include_prices: bool = True,
    ) -> tuple[str, int]:
        """
        Export products to CSV format.

        Returns:
            Tuple of (csv_content, records_count)
        """
        query = self.db.query(Product).options(
            joinedload(Product.category),
            joinedload(Product.brand_rel),
        )

        if source_app:
            query = query.filter(Product.source_app == source_app)
        if category_id:
            query = query.filter(Product.category_id == category_id)
        if brand_id:
            query = query.filter(Product.brand_id == brand_id)

        products = query.all()

        # Build CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        headers = [
            "ID", "Source App", "External ID", "Name", "Name (AR)",
            "SKU", "Barcode", "Category", "Brand", "Image URL",
            "Is Active", "First Seen", "Last Seen"
        ]
        if include_prices:
            headers.extend(["Current Price", "Original Price", "Currency", "Available"])

        writer.writerow(headers)

        # Data rows
        for product in products:
            row = [
                product.id,
                product.source_app,
                product.external_id,
                product.name,
                product.name_ar,
                product.sku,
                product.barcode,
                product.category.name if product.category else "",
                product.brand_rel.name if product.brand_rel else "",
                product.image_url,
                product.is_active,
                product.first_seen_at.isoformat() if product.first_seen_at else "",
                product.last_seen_at.isoformat() if product.last_seen_at else "",
            ]

            if include_prices:
                # Get latest price
                latest_price = (
                    self.db.query(PriceRecord)
                    .filter(PriceRecord.product_id == product.id)
                    .order_by(PriceRecord.recorded_at.desc())
                    .first()
                )
                if latest_price:
                    row.extend([
                        float(latest_price.price),
                        float(latest_price.original_price) if latest_price.original_price else "",
                        latest_price.currency,
                        latest_price.is_available,
                    ])
                else:
                    row.extend(["", "", "", ""])

            writer.writerow(row)

        return output.getvalue(), len(products)

    def export_prices_csv(
        self,
        source_app: Optional[str] = None,
        product_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> tuple[str, int]:
        """
        Export price history to CSV format.

        Returns:
            Tuple of (csv_content, records_count)
        """
        query = self.db.query(PriceRecord).options(
            joinedload(PriceRecord.product),
            joinedload(PriceRecord.unit),
        )

        if source_app:
            query = query.filter(PriceRecord.source_app == source_app)
        if product_id:
            query = query.filter(PriceRecord.product_id == product_id)
        if start_date:
            query = query.filter(PriceRecord.recorded_at >= start_date)
        if end_date:
            query = query.filter(PriceRecord.recorded_at <= end_date)

        # Limit to recent records for performance
        records = query.order_by(PriceRecord.recorded_at.desc()).limit(50000).all()

        # Build CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        headers = [
            "Record ID", "Product ID", "Product Name", "Source App",
            "Unit", "Price", "Original Price", "Discount %",
            "Currency", "Available", "Recorded At"
        ]
        writer.writerow(headers)

        # Data rows
        for record in records:
            writer.writerow([
                record.id,
                record.product_id,
                record.product.name if record.product else "",
                record.source_app,
                record.unit.name if record.unit else "Base",
                float(record.price),
                float(record.original_price) if record.original_price else "",
                float(record.discount_percentage) if record.discount_percentage else "",
                record.currency,
                record.is_available,
                record.recorded_at.isoformat() if record.recorded_at else "",
            ])

        return output.getvalue(), len(records)

    def export_comparison_csv(
        self,
        apps: Optional[List[str]] = None,
        category_id: Optional[int] = None,
    ) -> tuple[str, int]:
        """
        Export comparison data to CSV format.

        Returns:
            Tuple of (csv_content, records_count)
        """
        # Get products with barcodes that exist in multiple apps
        query = self.db.query(Product).filter(
            Product.barcode.isnot(None),
            Product.barcode != "",
        )

        if apps:
            query = query.filter(Product.source_app.in_(apps))
        if category_id:
            query = query.filter(Product.category_id == category_id)

        products = query.all()

        # Group by barcode
        barcode_groups: Dict[str, List[Product]] = {}
        for p in products:
            barcode = p.barcode.strip()
            if barcode:
                if barcode not in barcode_groups:
                    barcode_groups[barcode] = []
                barcode_groups[barcode].append(p)

        # Filter to products in multiple apps
        multi_app_barcodes = {
            bc: prods for bc, prods in barcode_groups.items()
            if len(set(p.source_app for p in prods)) > 1
        }

        # Build CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        headers = [
            "Barcode", "Product Name",
            "Ben Soliman Price", "Tager elSaada Price",
            "El Rabie Price", "Gomla Shoaib Price",
            "Lowest Price", "Highest Price", "Price Difference"
        ]
        writer.writerow(headers)

        # Data rows
        for barcode, prods in multi_app_barcodes.items():
            prices = {}
            primary_name = prods[0].name

            for p in prods:
                latest_price = (
                    self.db.query(PriceRecord)
                    .filter(PriceRecord.product_id == p.id)
                    .order_by(PriceRecord.recorded_at.desc())
                    .first()
                )
                if latest_price:
                    prices[p.source_app] = float(latest_price.price)

            price_values = list(prices.values())
            lowest = min(price_values) if price_values else None
            highest = max(price_values) if price_values else None

            writer.writerow([
                barcode,
                primary_name,
                prices.get("ben_soliman", ""),
                prices.get("tager_elsaada", ""),
                prices.get("el_rabie", ""),
                prices.get("gomla_shoaib", ""),
                lowest if lowest else "",
                highest if highest else "",
                highest - lowest if lowest and highest else "",
            ])

        return output.getvalue(), len(multi_app_barcodes)

    def get_image_urls_for_export(
        self,
        source_app: Optional[str] = None,
        category_id: Optional[int] = None,
        max_images: int = 1000,
    ) -> List[Dict[str, str]]:
        """
        Get image URLs for batch download.

        Returns:
            List of dicts with image_url, filename (based on barcode/sku)
        """
        query = self.db.query(Product).filter(
            Product.image_url.isnot(None),
            Product.image_url != "",
        )

        if source_app:
            query = query.filter(Product.source_app == source_app)
        if category_id:
            query = query.filter(Product.category_id == category_id)

        products = query.limit(max_images).all()

        images = []
        for product in products:
            # Determine filename
            if product.barcode:
                filename = f"{product.barcode}"
            elif product.sku:
                filename = f"{product.sku}"
            else:
                filename = f"{product.source_app}_{product.external_id}"

            # Get file extension from URL
            url = product.image_url
            ext = ".jpg"  # Default
            if url:
                if ".png" in url.lower():
                    ext = ".png"
                elif ".webp" in url.lower():
                    ext = ".webp"
                elif ".gif" in url.lower():
                    ext = ".gif"

            images.append({
                "product_id": product.id,
                "image_url": product.image_url,
                "filename": f"{filename}{ext}",
                "source_app": product.source_app,
            })

        return images

    def create_export_job(
        self,
        job_type: str,
        parameters: Dict[str, Any],
        requested_by: Optional[str] = None,
    ) -> ExportJob:
        """Create a new export job record."""
        job = ExportJob(
            job_type=job_type,
            status="pending",
            parameters=parameters,
            requested_by=requested_by,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def update_export_job(
        self,
        job_id: int,
        status: str,
        file_path: Optional[str] = None,
        file_name: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        records_count: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> Optional[ExportJob]:
        """Update export job status and results."""
        job = self.db.query(ExportJob).filter(ExportJob.id == job_id).first()
        if not job:
            return None

        job.status = status
        if file_path:
            job.file_path = file_path
        if file_name:
            job.file_name = file_name
        if file_size_bytes:
            job.file_size_bytes = file_size_bytes
        if records_count is not None:
            job.records_count = records_count
        if error_message:
            job.error_message = error_message

        if status == "processing" and not job.started_at:
            job.started_at = datetime.utcnow()
        elif status in ["completed", "failed"]:
            job.completed_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(job)
        return job

    def get_export_job(self, job_id: int) -> Optional[ExportJob]:
        """Get export job by ID."""
        return self.db.query(ExportJob).filter(ExportJob.id == job_id).first()

    def process_products_export(
        self,
        job_id: int,
        source_app: Optional[str] = None,
        category_id: Optional[int] = None,
        brand_id: Optional[int] = None,
        include_prices: bool = True,
    ) -> ExportJob:
        """Process a products export job synchronously."""
        job = self.get_export_job(job_id)
        if not job:
            raise ValueError("Job not found")

        try:
            self.update_export_job(job_id, "processing")

            csv_content, count = self.export_products_csv(
                source_app=source_app,
                category_id=category_id,
                brand_id=brand_id,
                include_prices=include_prices,
            )

            # Save to file
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"products_export_{timestamp}.csv"
            filepath = os.path.join(self.EXPORT_DIR, filename)

            with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
                f.write(csv_content)

            file_size = os.path.getsize(filepath)

            return self.update_export_job(
                job_id=job_id,
                status="completed",
                file_path=filepath,
                file_name=filename,
                file_size_bytes=file_size,
                records_count=count,
            )

        except Exception as e:
            return self.update_export_job(
                job_id=job_id,
                status="failed",
                error_message=str(e),
            )

    def process_prices_export(
        self,
        job_id: int,
        source_app: Optional[str] = None,
        product_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> ExportJob:
        """Process a prices export job synchronously."""
        job = self.get_export_job(job_id)
        if not job:
            raise ValueError("Job not found")

        try:
            self.update_export_job(job_id, "processing")

            csv_content, count = self.export_prices_csv(
                source_app=source_app,
                product_id=product_id,
                start_date=start_date,
                end_date=end_date,
            )

            # Save to file
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"prices_export_{timestamp}.csv"
            filepath = os.path.join(self.EXPORT_DIR, filename)

            with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
                f.write(csv_content)

            file_size = os.path.getsize(filepath)

            return self.update_export_job(
                job_id=job_id,
                status="completed",
                file_path=filepath,
                file_name=filename,
                file_size_bytes=file_size,
                records_count=count,
            )

        except Exception as e:
            return self.update_export_job(
                job_id=job_id,
                status="failed",
                error_message=str(e),
            )

    def process_comparison_export(
        self,
        job_id: int,
        apps: Optional[List[str]] = None,
        category_id: Optional[int] = None,
    ) -> ExportJob:
        """Process a comparison export job synchronously."""
        job = self.get_export_job(job_id)
        if not job:
            raise ValueError("Job not found")

        try:
            self.update_export_job(job_id, "processing")

            csv_content, count = self.export_comparison_csv(
                apps=apps,
                category_id=category_id,
            )

            # Save to file
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"comparison_export_{timestamp}.csv"
            filepath = os.path.join(self.EXPORT_DIR, filename)

            with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
                f.write(csv_content)

            file_size = os.path.getsize(filepath)

            return self.update_export_job(
                job_id=job_id,
                status="completed",
                file_path=filepath,
                file_name=filename,
                file_size_bytes=file_size,
                records_count=count,
            )

        except Exception as e:
            return self.update_export_job(
                job_id=job_id,
                status="failed",
                error_message=str(e),
            )
