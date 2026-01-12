"""Script to scrape Ben Soliman products and store in database."""
import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import select

from src.database.connection import get_async_session, init_db
from src.models.database import Product, Category, Brand, PriceRecord, ScrapeJob
from src.models.enums import SourceApp

# Ben Soliman API Configuration
BASE_URL = "http://41.65.168.38:8001"
JWT_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIzMjI4NDYiLCJleHAiOjIwODM1Mzg0ODksImlhdCI6MTc2ODE3ODQ4OX0.su9Of2FRKna5mkZEQSTVYAVyGnhZAFz6KiSB06Ec_E4"

# Image server URL
IMAGE_SERVER = "http://37.148.206.212"

HEADERS = {
    "user-agent": "Dart/3.9 (dart:io)",
    "accept-language": "ar",
    "accept-encoding": "gzip",
    "os": "android",
    "authorization": f"Bearer {JWT_TOKEN}",
}

# Project root for image storage
PROJECT_ROOT = Path(__file__).parent.parent
IMAGES_DIR = PROJECT_ROOT / "static" / "images" / "products"


async def download_image(client: httpx.AsyncClient, image_name: str, product_id: str) -> str | None:
    """Download product image and save locally.

    Based on mitmproxy analysis:
    - Images are at /ItemImage/{ImageName} (not /Icons/)
    - ImageName field from API contains the actual filename
    - Examples: 4020801.png, 1_zoUHf1Q.png, etc.
    """
    if not image_name:
        return None

    # Create images directory if needed
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    # Generate local filename (use product_id for consistency)
    ext = Path(image_name).suffix or ".png"
    local_filename = f"ben_soliman_{product_id}{ext}"
    local_path = IMAGES_DIR / local_filename

    # Skip if already downloaded
    if local_path.exists():
        return f"/static/images/products/{local_filename}"

    # Use ImageName directly - this is the correct pattern!
    url = f"{IMAGE_SERVER}/ItemImage/{image_name}"

    try:
        response = await client.get(url, headers=HEADERS, timeout=15.0)
        if response.status_code == 200 and len(response.content) > 500:
            # Verify it's actually an image (check magic bytes)
            content = response.content
            is_png = content[:4] == b'\x89PNG'
            is_jpg = content[:2] == b'\xff\xd8'
            is_gif = content[:6] == b'GIF89a' or content[:6] == b'GIF87a'

            if is_png or is_jpg or is_gif:
                with open(local_path, "wb") as f:
                    f.write(content)
                return f"/static/images/products/{local_filename}"
    except Exception:
        pass

    return None


async def fetch_categories(client: httpx.AsyncClient) -> list:
    """Fetch categories from Ben Soliman API."""
    print("Fetching categories...")
    resp = await client.get(
        f"{BASE_URL}/customer_app/api/v2/categories",
        params={"domain_id": 2},
        headers=HEADERS,
    )
    data = resp.json()
    categories = data.get("categories", [])
    print(f"Found {len(categories)} categories")
    return categories


async def fetch_products(client: httpx.AsyncClient, category_id: int = None) -> list:
    """Fetch products from Ben Soliman API."""
    params = {"domain_id": 2}
    if category_id:
        params["category_id"] = category_id

    resp = await client.get(
        f"{BASE_URL}/customer_app/api/v2/items",
        params=params,
        headers=HEADERS,
    )
    data = resp.json()
    return data.get("data", [])


async def fetch_brands(client: httpx.AsyncClient) -> list:
    """Fetch brands from Ben Soliman API."""
    print("Fetching brands...")
    resp = await client.get(
        f"{BASE_URL}/customer_app/api/v2/brands",
        params={"domain_id": 2},
        headers=HEADERS,
    )
    data = resp.json()
    brands = data.get("Brands", [])
    print(f"Found {len(brands)} brands")
    return brands


async def main():
    """Main scraping function."""
    print("=" * 50)
    print("Ben Soliman Scraper")
    print("=" * 50)

    # Initialize database
    print("\nInitializing database...")
    await init_db()
    print("Database ready!")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Create scrape job
        async with get_async_session() as session:
            job = ScrapeJob(
                source_app=SourceApp.BEN_SOLIMAN.value,
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
                cat_id = str(cat_data.get("category_Id", ""))

                # Check if category exists
                result = await session.execute(
                    select(Category).where(
                        Category.source_app == SourceApp.BEN_SOLIMAN.value,
                        Category.external_id == cat_id,
                    )
                )
                existing = result.scalar_one_or_none()

                if not existing:
                    category = Category(
                        source_app=SourceApp.BEN_SOLIMAN.value,
                        external_id=cat_id,
                        name=cat_data.get("Name", ""),
                        name_ar=cat_data.get("Name"),
                        image_url=f"{IMAGE_SERVER}/ItemImage/{cat_data.get('ImageName')}" if cat_data.get("ImageName") else None,
                    )
                    session.add(category)

            await session.commit()
            print(f"Stored {len(categories)} categories")

            # Build category mapping: external_id -> database_id
            category_map = {}
            cat_result = await session.execute(
                select(Category).where(Category.source_app == SourceApp.BEN_SOLIMAN.value)
            )
            for cat in cat_result.scalars():
                category_map[cat.external_id] = cat.id
            print(f"Built category map with {len(category_map)} entries")

        # Fetch and store brands
        brands = await fetch_brands(client)

        async with get_async_session() as session:
            for brand_data in brands:
                brand_id = str(brand_data.get("Brand_Id", ""))

                # Check if brand exists
                result = await session.execute(
                    select(Brand).where(
                        Brand.source_app == SourceApp.BEN_SOLIMAN.value,
                        Brand.external_id == brand_id,
                    )
                )
                existing = result.scalar_one_or_none()

                if not existing:
                    brand = Brand(
                        source_app=SourceApp.BEN_SOLIMAN.value,
                        external_id=brand_id,
                        name=brand_data.get("Name", ""),
                        name_ar=brand_data.get("Name"),
                        image_url=f"{IMAGE_SERVER}/ItemImage/{brand_data.get('ImageName')}" if brand_data.get("ImageName") else None,
                    )
                    session.add(brand)

            await session.commit()
            print(f"Stored {len(brands)} brands")

            # Build brand mapping: external_id -> database_id
            brand_map = {}
            brand_result = await session.execute(
                select(Brand).where(Brand.source_app == SourceApp.BEN_SOLIMAN.value)
            )
            for b in brand_result.scalars():
                brand_map[b.external_id] = b.id
            print(f"Built brand map with {len(brand_map)} entries")

        # Fetch all products
        print("\nFetching products...")
        all_products = await fetch_products(client)
        print(f"Found {len(all_products)} products")

        # Store products and prices
        products_new = 0
        products_updated = 0
        images_downloaded = 0

        async with get_async_session() as session:
            for prod_data in all_products:
                external_id = str(prod_data.get("ItemCode", ""))

                # Get category database ID from CategoryCode
                category_code = str(prod_data.get("CategoryCode", ""))
                category_db_id = category_map.get(category_code)

                # Get brand database ID from BrandId
                brand_ext_id = str(prod_data.get("BrandId", ""))
                brand_db_id = brand_map.get(brand_ext_id)

                # Check if product exists
                result = await session.execute(
                    select(Product).where(
                        Product.source_app == SourceApp.BEN_SOLIMAN.value,
                        Product.external_id == external_id,
                    )
                )
                existing = result.scalar_one_or_none()

                # Get price info
                sell_price = prod_data.get("SellPrice") or prod_data.get("ItemPrice")
                item_price = prod_data.get("ItemPrice")

                # Calculate discount
                discount_pct = None
                if sell_price and item_price and float(item_price) > float(sell_price):
                    discount_pct = round((1 - float(sell_price) / float(item_price)) * 100, 2)

                # Download image
                image_name = prod_data.get("ImageName")
                local_image_path = await download_image(client, image_name, external_id)
                # Keep original URL as fallback (using correct /ItemImage/ path)
                original_image_url = f"{IMAGE_SERVER}/ItemImage/{image_name}" if image_name else None

                if existing:
                    # Update existing product
                    existing.name = prod_data.get("Name", "")
                    existing.name_ar = prod_data.get("Name")
                    existing.description = prod_data.get("Description")
                    existing.image_url = local_image_path or original_image_url
                    existing.barcode = prod_data.get("BarCode")
                    existing.category_id = category_db_id  # Link to category
                    existing.brand_id = brand_db_id  # Link to brand
                    existing.brand = str(prod_data.get("BrandId")) if prod_data.get("BrandId") else None
                    existing.last_seen_at = datetime.now(timezone.utc)
                    product = existing
                    products_updated += 1
                else:
                    # Create new product
                    product = Product(
                        source_app=SourceApp.BEN_SOLIMAN.value,
                        external_id=external_id,
                        name=prod_data.get("Name", ""),
                        name_ar=prod_data.get("Name"),
                        description=prod_data.get("Description"),
                        description_ar=prod_data.get("Description"),
                        brand=str(prod_data.get("BrandId")) if prod_data.get("BrandId") else None,
                        brand_id=brand_db_id,  # Link to brand
                        sku=external_id,
                        barcode=prod_data.get("BarCode"),
                        image_url=local_image_path or original_image_url,
                        category_id=category_db_id,  # Link to category
                        unit_type="piece",
                        min_order_quantity=prod_data.get("MinimumQuantity", 1),
                        is_active=True,
                    )
                    session.add(product)
                    await session.flush()  # Get the product ID
                    products_new += 1

                # Create price record
                if sell_price:
                    price_record = PriceRecord(
                        product_id=product.id,
                        source_app=SourceApp.BEN_SOLIMAN.value,
                        price=Decimal(str(sell_price)),
                        original_price=Decimal(str(item_price)) if item_price else None,
                        discount_percentage=Decimal(str(discount_pct)) if discount_pct else None,
                        is_available=prod_data.get("Balance", 0) > 0,
                        scrape_job_id=job_id,
                    )
                    session.add(price_record)

                # Count downloaded images
                if local_image_path:
                    images_downloaded += 1

                # Progress indicator
                total = products_new + products_updated
                if total % 50 == 0:
                    print(f"  Processed {total} products, {images_downloaded} images downloaded...")

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
        print(f"Total: {products_new + products_updated}")
        print(f"Images downloaded: {images_downloaded}")
        print(f"\nImages saved to: {IMAGES_DIR}")
        print("\nRefresh your dashboard to see the data!")


if __name__ == "__main__":
    asyncio.run(main())
