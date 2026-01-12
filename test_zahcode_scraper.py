"""
Test script for ZAH CODE scrapers (El Rabie & Gomla Shoaib).
Runs standalone without full project dependencies.
"""
import sys
import io

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import requests
import psycopg2
import json
import random
import re
from datetime import datetime, timezone
from decimal import Decimal

# Database connection
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "competitor_data",
    "user": "scraper",
    "password": "scraper123"
}

# ZAH CODE Apps Configuration
APPS = {
    "el_rabie": {
        "name": "El Rabie",
        "name_ar": "شركة الربيع",
        "base_url": "https://gomletalrabia.zahcode.online/api/",
        "http_method": "GET",  # El Rabie uses GET for products
    },
    "gomla_shoaib": {
        "name": "Gomla Shoaib",
        "name_ar": "جملة شعيب",
        "base_url": "https://gomletshoaib.zahcode.online/api/",
        "http_method": "POST",  # Gomla Shoaib requires POST for products
    }
}

# Registration data
REG_DATA = {
    "password": "scraper123456",
    "name": "Scraper Bot",
    "city": "Cairo",
    "address": "Test Address",
    "location": "Cairo, Egypt",
    "balance": "0",
    "longitude": "31.2357",
    "latitude": "30.0444",
    "type": "user",
}


def get_fresh_token(base_url: str) -> str:
    """Register a new account and get fresh token."""
    phone = f"010{random.randint(10000000, 99999999)}"
    email = f"scraper{random.randint(1000, 9999)}@scraper.local"

    reg_data = {
        **REG_DATA,
        "mobile": phone,
        "email": email,
    }

    try:
        resp = requests.post(f"{base_url}auth/register", data=reg_data, timeout=30)
        data = resp.json()
        if "access_token" in data:
            print(f"  Registered with phone: {phone}")
            return data["access_token"]
        else:
            print(f"  Registration failed: {data}")
            return None
    except Exception as e:
        print(f"  Registration error: {e}")
        return None


def fetch_categories(base_url: str, token: str) -> list:
    """Fetch all categories."""
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = requests.get(f"{base_url}category/all", headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception as e:
        print(f"  Error fetching categories: {e}")
        return []


def fetch_products_by_category(base_url: str, token: str, category_id: int, http_method: str = "GET") -> list:
    """Fetch products for a specific category.

    Args:
        base_url: API base URL
        token: Authentication token
        category_id: Category ID to fetch products for
        http_method: HTTP method to use (GET or POST). Gomla Shoaib requires POST.
    """
    headers = {"Authorization": f"Bearer {token}"}
    try:
        if http_method == "POST":
            resp = requests.post(
                f"{base_url}products/category_id",
                headers=headers,
                params={"category_id": category_id},
                timeout=30
            )
        else:
            resp = requests.get(
                f"{base_url}products/category_id",
                headers=headers,
                params={"category_id": category_id},
                timeout=30
            )
        if resp.status_code == 200:
            data = resp.json()
            # Handle case where API returns dict (error/empty) instead of list
            if isinstance(data, list):
                return data
            return []
        return []
    except Exception as e:
        print(f"  Error fetching products for category {category_id}: {e}")
        return []


def clean_description(desc: str) -> str:
    """Remove HTML tags from description."""
    if desc:
        return re.sub(r'<[^>]+>', '', desc).strip()
    return ""


def parse_unit(unit_str: str) -> str:
    """Parse Arabic unit to English."""
    unit_mapping = {
        "قطعة": "piece", "وحدة": "piece", "علبة": "box",
        "باكت": "pack", "عبوة": "pack", "كرتونة": "carton",
        "كرتون": "carton", "دستة": "carton", "كيلو": "kg",
        "جرام": "gram", "لتر": "liter",
    }
    if unit_str:
        return unit_mapping.get(unit_str, "piece")
    return "piece"


def save_to_database(source_app: str, categories: list, products: list):
    """Save scraped data to PostgreSQL database."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    now = datetime.now(timezone.utc)

    # Stats
    stats = {
        "categories_new": 0,
        "categories_updated": 0,
        "products_new": 0,
        "products_updated": 0,
        "units_new": 0,
        "prices_recorded": 0,
    }

    # Create scrape job
    cur.execute("""
        INSERT INTO scrape_jobs (source_app, job_type, status, started_at)
        VALUES (%s, %s, %s, %s)
        RETURNING id
    """, (source_app, "full", "running", now))
    job_id = cur.fetchone()[0]
    conn.commit()

    try:
        # Save categories
        print(f"  Saving {len(categories)} categories...")
        for cat in categories:
            cur.execute("""
                INSERT INTO categories (source_app, external_id, name, name_ar, image_url, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_app, external_id)
                DO UPDATE SET name = EXCLUDED.name, name_ar = EXCLUDED.name_ar,
                              image_url = EXCLUDED.image_url, updated_at = EXCLUDED.updated_at
                RETURNING id, (xmax = 0) as is_new
            """, (
                source_app,
                str(cat.get("id")),
                cat.get("name", ""),
                cat.get("name"),
                cat.get("image"),
                now, now
            ))
            result = cur.fetchone()
            if result[1]:
                stats["categories_new"] += 1
            else:
                stats["categories_updated"] += 1

        conn.commit()

        # Get category ID mapping
        cur.execute("""
            SELECT external_id, id FROM categories WHERE source_app = %s
        """, (source_app,))
        cat_map = {row[0]: row[1] for row in cur.fetchall()}

        # Save products
        print(f"  Saving {len(products)} products...")
        for prod in products:
            ext_id = str(prod.get("id", ""))
            cat_ext_id = str(prod.get("category_id", ""))
            cat_db_id = cat_map.get(cat_ext_id)

            # Get price from variants
            variants = prod.get("variants", [])
            primary = variants[0] if variants else {}
            price = primary.get("discounted_price") or primary.get("price") or 0
            original_price = primary.get("price")
            unit_name = primary.get("unit", "piece")

            stock = prod.get("stock", 0)
            is_available = stock > 0

            # Insert/update product
            cur.execute("""
                INSERT INTO products (
                    source_app, external_id, name, name_ar, description, description_ar,
                    category_id, sku, image_url, unit_type, min_order_quantity,
                    extra_data, is_active, first_seen_at, last_seen_at, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_app, external_id)
                DO UPDATE SET
                    name = EXCLUDED.name, name_ar = EXCLUDED.name_ar,
                    description = EXCLUDED.description, description_ar = EXCLUDED.description_ar,
                    category_id = EXCLUDED.category_id, image_url = EXCLUDED.image_url,
                    extra_data = EXCLUDED.extra_data, is_active = EXCLUDED.is_active,
                    last_seen_at = EXCLUDED.last_seen_at, updated_at = EXCLUDED.updated_at
                RETURNING id, (xmax = 0) as is_new
            """, (
                source_app, ext_id,
                prod.get("name", ""), prod.get("name"),
                clean_description(prod.get("description")),
                clean_description(prod.get("description")),
                cat_db_id, ext_id,
                prod.get("image"),
                parse_unit(unit_name),
                1,
                json.dumps({
                    "stock": stock,
                    "total_allowed_quantity": prod.get("total_allowed_quantity"),
                    "category_name": prod.get("category_name"),
                    "variants": variants,
                }),
                is_available,
                now, now, now, now
            ))
            result = cur.fetchone()
            product_id = result[0]
            is_new = result[1]

            if is_new:
                stats["products_new"] += 1
            else:
                stats["products_updated"] += 1

            # Save product units (variants)
            for var in variants:
                var_id = str(var.get("id", ""))
                var_unit = var.get("unit", "piece")
                var_price = var.get("discounted_price") or var.get("price") or 0
                var_orig_price = var.get("price")

                # Insert unit
                cur.execute("""
                    INSERT INTO product_units (
                        product_id, external_id, name, name_ar, factor,
                        min_quantity, is_active, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (product_id, external_id)
                    DO UPDATE SET name = EXCLUDED.name, name_ar = EXCLUDED.name_ar, updated_at = EXCLUDED.updated_at
                    RETURNING id, (xmax = 0) as is_new
                """, (
                    product_id, var_id,
                    parse_unit(var_unit), var_unit,
                    var.get("measurement", 1),
                    var.get("offer_quantity", 1),
                    True, now, now
                ))
                unit_result = cur.fetchone()
                unit_id = unit_result[0]
                if unit_result[1]:
                    stats["units_new"] += 1

                # Record price for this unit
                cur.execute("""
                    INSERT INTO price_records (
                        product_id, unit_id, source_app, price, original_price,
                        currency, is_available, recorded_at, scrape_job_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    product_id, unit_id, source_app,
                    var_price, var_orig_price,
                    "EGP", is_available, now, job_id
                ))
                stats["prices_recorded"] += 1

        conn.commit()

        # Update job as completed
        cur.execute("""
            UPDATE scrape_jobs SET
                status = 'completed',
                completed_at = %s,
                products_scraped = %s,
                products_new = %s,
                products_updated = %s
            WHERE id = %s
        """, (now, stats["products_new"] + stats["products_updated"],
              stats["products_new"], stats["products_updated"], job_id))
        conn.commit()

        return stats

    except Exception as e:
        conn.rollback()
        cur.execute("""
            UPDATE scrape_jobs SET status = 'failed', completed_at = %s,
                   error_details = %s WHERE id = %s
        """, (now, json.dumps({"error": str(e)}), job_id))
        conn.commit()
        raise
    finally:
        cur.close()
        conn.close()


def scrape_app(source_app: str, config: dict):
    """Scrape a single ZAH CODE app."""
    print(f"\n{'='*60}")
    print(f"Scraping {config['name']} ({config['name_ar']})")
    print(f"Base URL: {config['base_url']}")
    print(f"HTTP Method: {config.get('http_method', 'GET')}")
    print("="*60)

    base_url = config["base_url"]
    http_method = config.get("http_method", "GET")

    # Get fresh token
    print("\n1. Getting authentication token...")
    token = get_fresh_token(base_url)
    if not token:
        print("  FAILED to get token!")
        return
    print(f"  Token acquired: {token[:50]}...")

    # Fetch categories
    print("\n2. Fetching categories...")
    categories = fetch_categories(base_url, token)
    print(f"  Found {len(categories)} categories")

    if not categories:
        print("  No categories found, skipping...")
        return

    # Fetch products by category
    print("\n3. Fetching products by category...")
    all_products = []
    seen_ids = set()

    for i, cat in enumerate(categories):
        cat_id = cat.get("id")
        cat_name = cat.get("name", "Unknown")

        # Get fresh token for each category (tokens expire quickly)
        if i % 5 == 0 and i > 0:
            token = get_fresh_token(base_url)
            if not token:
                print(f"  Failed to refresh token at category {i}")
                continue

        products = fetch_products_by_category(base_url, token, cat_id, http_method)

        for prod in products:
            prod_id = prod.get("id")
            if prod_id and prod_id not in seen_ids:
                seen_ids.add(prod_id)
                prod["category_id"] = cat_id
                prod["category_name"] = cat_name
                all_products.append(prod)

        print(f"  [{i+1}/{len(categories)}] {cat_name}: {len(products)} products")

    print(f"\n  Total unique products: {len(all_products)}")

    # Save to database
    print("\n4. Saving to database...")
    try:
        stats = save_to_database(source_app, categories, all_products)
        print(f"\n  RESULTS:")
        print(f"  - Categories: {stats['categories_new']} new, {stats['categories_updated']} updated")
        print(f"  - Products: {stats['products_new']} new, {stats['products_updated']} updated")
        print(f"  - Units: {stats['units_new']} new")
        print(f"  - Price records: {stats['prices_recorded']}")
    except Exception as e:
        print(f"  ERROR saving to database: {e}")
        raise


def main():
    print("ZAH CODE Scraper Test")
    print("=" * 60)

    # Test database connection first
    print("\nTesting database connection...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM products")
        count = cur.fetchone()[0]
        print(f"  Connected! Current product count: {count}")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"  Database connection FAILED: {e}")
        return

    # Scrape each app
    for source_app, config in APPS.items():
        try:
            scrape_app(source_app, config)
        except Exception as e:
            print(f"\nERROR scraping {source_app}: {e}")
            continue

    # Final summary
    print("\n" + "=" * 60)
    print("FINAL DATABASE STATE")
    print("=" * 60)

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        SELECT source_app, COUNT(*) FROM products GROUP BY source_app ORDER BY source_app
    """)
    print("\nProducts by source:")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}")

    cur.execute("""
        SELECT source_app, COUNT(*) FROM categories GROUP BY source_app ORDER BY source_app
    """)
    print("\nCategories by source:")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}")

    cur.execute("""
        SELECT source_app, COUNT(*) FROM product_units pu
        JOIN products p ON pu.product_id = p.id
        GROUP BY source_app ORDER BY source_app
    """)
    print("\nProduct units by source:")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}")

    cur.execute("""
        SELECT source_app, COUNT(*) FROM price_records GROUP BY source_app ORDER BY source_app
    """)
    print("\nPrice records by source:")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}")

    cur.close()
    conn.close()

    print("\nDone!")


if __name__ == "__main__":
    main()
