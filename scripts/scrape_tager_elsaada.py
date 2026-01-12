"""Script to scrape Tager elSa3ada products and store in database."""
import asyncio
import sys
import os
from pathlib import Path

# Fix Windows console encoding for Arabic text
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import select

from src.database.connection import get_async_session, init_db
from src.models.database import Product, Category, Brand, PriceRecord, ProductUnit, ScrapeJob
from src.models.enums import SourceApp

# Tager elSa3ada API Configuration
BASE_URL = "https://app.tagerelsa3ada.com/api"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Dart/3.0 (dart:io)",
    "Accept-Language": "ar",
}

# Project root for image storage
PROJECT_ROOT = Path(__file__).parent.parent
IMAGES_DIR = PROJECT_ROOT / "static" / "images" / "products"


async def download_image(client: httpx.AsyncClient, image_url: str, product_id: str) -> str | None:
    """Download product image and save locally."""
    if not image_url:
        return None

    # Create images directory if needed
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    # Generate local filename
    ext = ".webp"  # Tager uses webp images
    local_filename = f"tager_elsaada_{product_id}{ext}"
    local_path = IMAGES_DIR / local_filename

    # Skip if already downloaded
    if local_path.exists():
        return f"/static/images/products/{local_filename}"

    try:
        # The URL already has signed parameters, use it directly
        response = await client.get(image_url, timeout=15.0)
        if response.status_code == 200 and len(response.content) > 500:
            with open(local_path, "wb") as f:
                f.write(response.content)
            return f"/static/images/products/{local_filename}"
    except Exception:
        pass

    return None


async def fetch_categories(client: httpx.AsyncClient) -> list:
    """Fetch categories from Tager elSa3ada API."""
    print("Fetching categories...")
    resp = await client.get(
        f"{BASE_URL}/v1/categories",
        headers=HEADERS,
    )
    data = resp.json()
    categories = data.get("data", [])
    print(f"Found {len(categories)} categories")
    return categories


async def fetch_vendors(client: httpx.AsyncClient) -> list:
    """Fetch vendors (brands) from Tager elSa3ada API."""
    print("Fetching vendors...")
    all_vendors = []
    page = 1

    while True:
        resp = await client.get(
            f"{BASE_URL}/v1/attributes/vendors",
            params={"page": page, "per_page": 100},
            headers=HEADERS,
        )
        data = resp.json()
        vendors = data.get("data", {}).get("data", [])

        if not vendors:
            break

        all_vendors.extend(vendors)

        meta = data.get("data", {}).get("meta", {})
        if page >= meta.get("last_page", 1):
            break
        page += 1

    print(f"Found {len(all_vendors)} vendors")
    return all_vendors


async def fetch_products(client: httpx.AsyncClient, page: int = 1, per_page: int = 100) -> dict:
    """Fetch products from Tager elSa3ada API."""
    resp = await client.get(
        f"{BASE_URL}/v1/products",
        params={"page": page, "per_page": per_page},
        headers=HEADERS,
    )
    return resp.json()


async def main():
    """Main scraping function."""
    print("=" * 50)
    print("Tager elSa3ada Scraper")
    print("=" * 50)

    # Initialize database
    print("\nInitializing database...")
    await init_db()
    print("Database ready!")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Create scrape job
        async with get_async_session() as session:
            job = ScrapeJob(
                source_app=SourceApp.TAGER_ELSAADA.value,
                job_type="full",
                status="running",
                started_at=datetime.now(timezone.utc),
            )
            session.add(job)
            await session.commit()
            job_id = job.id
            print(f"\nCreated scrape job #{job_id}")

        # Fetch and store categories
        categories = await fetch_categories(client)

        async with get_async_session() as session:
            for cat_data in categories:
                cat_id = str(cat_data.get("id", ""))

                # Check if category exists
                result = await session.execute(
                    select(Category).where(
                        Category.source_app == SourceApp.TAGER_ELSAADA.value,
                        Category.external_id == cat_id,
                    )
                )
                existing = result.scalar_one_or_none()

                if not existing:
                    # Get image URL
                    images = cat_data.get("images", {})
                    image_url = images.get("logo_url") if images else None

                    category = Category(
                        source_app=SourceApp.TAGER_ELSAADA.value,
                        external_id=cat_id,
                        name=cat_data.get("name", ""),
                        name_ar=cat_data.get("name"),
                        image_url=image_url,
                        sort_order=cat_data.get("position", 0),
                    )
                    session.add(category)

            await session.commit()
            print(f"Stored {len(categories)} categories")

            # Build category mapping: external_id -> database_id
            category_map = {}
            cat_result = await session.execute(
                select(Category).where(Category.source_app == SourceApp.TAGER_ELSAADA.value)
            )
            for cat in cat_result.scalars():
                category_map[cat.external_id] = cat.id
            print(f"Built category map with {len(category_map)} entries")

        # Fetch and store vendors (brands)
        vendors = await fetch_vendors(client)

        async with get_async_session() as session:
            for vendor_data in vendors:
                vendor_id = str(vendor_data.get("id", ""))

                # Check if vendor exists
                result = await session.execute(
                    select(Brand).where(
                        Brand.source_app == SourceApp.TAGER_ELSAADA.value,
                        Brand.external_id == vendor_id,
                    )
                )
                existing = result.scalar_one_or_none()

                if not existing:
                    brand = Brand(
                        source_app=SourceApp.TAGER_ELSAADA.value,
                        external_id=vendor_id,
                        name=vendor_data.get("name", ""),
                        name_ar=vendor_data.get("name"),
                        image_url=vendor_data.get("image_url"),
                    )
                    session.add(brand)

            await session.commit()
            print(f"Stored {len(vendors)} vendors")

            # Build vendor mapping: external_id -> database_id
            vendor_map = {}
            vendor_result = await session.execute(
                select(Brand).where(Brand.source_app == SourceApp.TAGER_ELSAADA.value)
            )
            for v in vendor_result.scalars():
                vendor_map[v.external_id] = v.id
            print(f"Built vendor map with {len(vendor_map)} entries")

        # Fetch all products with pagination
        print("\nFetching products...")

        # Get total count first
        first_page = await fetch_products(client, page=1, per_page=1)
        total_products = first_page.get("data", {}).get("meta", {}).get("total", 0)
        print(f"Total products to fetch: {total_products}")

        # Store products and prices
        products_new = 0
        products_updated = 0
        units_created = 0
        images_downloaded = 0
        page = 1
        per_page = 100

        async with get_async_session() as session:
            while True:
                response = await fetch_products(client, page=page, per_page=per_page)
                products_data = response.get("data", {}).get("data", [])

                if not products_data:
                    break

                for prod_data in products_data:
                    external_id = str(prod_data.get("id", ""))
                    sku = prod_data.get("sku", "")

                    # Get vendor (brand) database ID
                    vendor_info = prod_data.get("vendor")
                    vendor_db_id = None
                    vendor_name = None
                    if vendor_info:
                        vendor_ext_id = str(vendor_info.get("id", ""))
                        vendor_db_id = vendor_map.get(vendor_ext_id)
                        vendor_name = vendor_info.get("name")

                    # Check if product exists
                    result = await session.execute(
                        select(Product).where(
                            Product.source_app == SourceApp.TAGER_ELSAADA.value,
                            Product.external_id == external_id,
                        )
                    )
                    existing = result.scalar_one_or_none()

                    # Get image URL
                    base_image = prod_data.get("base_image", {})
                    original_image_url = base_image.get("url") if base_image else None

                    # Download image
                    local_image_path = await download_image(client, original_image_url, external_id)

                    # Get units data - Tager has units with prices
                    units_data = prod_data.get("units", [])

                    # Get barcode from first unit for product-level storage
                    first_barcode = None
                    if units_data:
                        bc = units_data[0].get("barcode", "")
                        first_barcode = bc.split(",")[0] if bc else None

                    if existing:
                        # Update existing product
                        existing.name = prod_data.get("name", "")
                        existing.name_ar = prod_data.get("name")
                        existing.description = prod_data.get("description")
                        existing.image_url = local_image_path or original_image_url
                        existing.barcode = first_barcode
                        existing.sku = sku
                        existing.brand_id = vendor_db_id
                        existing.brand = vendor_name
                        existing.last_seen_at = datetime.now(timezone.utc)
                        product = existing
                        products_updated += 1
                    else:
                        # Create new product
                        product = Product(
                            source_app=SourceApp.TAGER_ELSAADA.value,
                            external_id=external_id,
                            name=prod_data.get("name", ""),
                            name_ar=prod_data.get("name"),
                            description=prod_data.get("description"),
                            description_ar=prod_data.get("description"),
                            brand=vendor_name,
                            brand_id=vendor_db_id,
                            sku=sku,
                            barcode=first_barcode,
                            image_url=local_image_path or original_image_url,
                            unit_type="piece",
                            is_active=True,
                        )
                        session.add(product)
                        await session.flush()  # Get the product ID
                        products_new += 1

                    # Process all units with their individual prices
                    if units_data:
                        for idx, unit_data in enumerate(units_data):
                            unit_id_str = str(unit_data.get("id", f"{external_id}_{idx}"))
                            unit_name = unit_data.get("name", "قطعة")
                            factor = unit_data.get("factor", 1) or 1
                            unit_barcode = unit_data.get("barcode", "").split(",")[0] if unit_data.get("barcode") else None
                            is_base = unit_data.get("base_unit", False) or (idx == 0)
                            price = unit_data.get("price")
                            old_price = unit_data.get("old_price")
                            in_stock = unit_data.get("in_stock", False)

                            # Check if unit exists
                            unit_result = await session.execute(
                                select(ProductUnit).where(
                                    ProductUnit.product_id == product.id,
                                    ProductUnit.external_id == unit_id_str,
                                )
                            )
                            existing_unit = unit_result.scalar_one_or_none()

                            if existing_unit:
                                existing_unit.name = unit_name
                                existing_unit.name_ar = unit_name
                                existing_unit.factor = factor
                                existing_unit.barcode = unit_barcode
                                existing_unit.is_base_unit = is_base
                                unit = existing_unit
                            else:
                                unit = ProductUnit(
                                    product_id=product.id,
                                    external_id=unit_id_str,
                                    name=unit_name,
                                    name_ar=unit_name,
                                    factor=factor,
                                    barcode=unit_barcode,
                                    is_base_unit=is_base,
                                    is_active=True,
                                )
                                session.add(unit)
                                await session.flush()
                                units_created += 1

                            # Create price record for this unit
                            if price:
                                discount_pct = None
                                if old_price and float(old_price) > float(price):
                                    discount_pct = round((1 - float(price) / float(old_price)) * 100, 2)

                                price_record = PriceRecord(
                                    product_id=product.id,
                                    unit_id=unit.id,
                                    source_app=SourceApp.TAGER_ELSAADA.value,
                                    price=Decimal(str(price)),
                                    original_price=Decimal(str(old_price)) if old_price and old_price > 0 else None,
                                    discount_percentage=Decimal(str(discount_pct)) if discount_pct else None,
                                    is_available=in_stock,
                                    scrape_job_id=job_id,
                                )
                                session.add(price_record)

                    # Count downloaded images
                    if local_image_path:
                        images_downloaded += 1

                # Progress indicator
                total = products_new + products_updated
                print(f"  Processed {total} products, {units_created} units, {images_downloaded} images...")

                # Check if we have more pages
                meta = response.get("data", {}).get("meta", {})
                if page >= meta.get("last_page", 1):
                    break
                page += 1

            await session.commit()

        # Update job status
        async with get_async_session() as session:
            result = await session.execute(
                select(ScrapeJob).where(ScrapeJob.id == job_id)
            )
            job = result.scalar_one()
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            job.products_scraped = products_new + products_updated
            job.products_new = products_new
            job.products_updated = products_updated
            await session.commit()

        print("\n" + "=" * 50)
        print("Scraping Complete!")
        print("=" * 50)
        print(f"New products: {products_new}")
        print(f"Updated products: {products_updated}")
        print(f"Total products: {products_new + products_updated}")
        print(f"Units created: {units_created}")
        print(f"Images downloaded: {images_downloaded}")
        print(f"\nImages saved to: {IMAGES_DIR}")
        print("\nRefresh your dashboard to see the data!")


if __name__ == "__main__":
    asyncio.run(main())
