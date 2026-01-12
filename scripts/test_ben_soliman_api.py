"""Quick test script to verify Ben Soliman API access."""
import httpx
import json
import sys

# Fix Windows console encoding
sys.stdout.reconfigure(encoding='utf-8')

# API Configuration - Two servers discovered
BASE_URL_1 = "http://41.65.168.38:8001"  # Primary
BASE_URL_2 = "http://37.148.206.212:5005"  # Secondary
JWT_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIzMjI4NDYiLCJleHAiOjIwODM1Mzg0ODksImlhdCI6MTc2ODE3ODQ4OX0.su9Of2FRKna5mkZEQSTVYAVyGnhZAFz6KiSB06Ec_E4"

HEADERS = {
    "user-agent": "Dart/3.9 (dart:io)",
    "accept-language": "ar",
    "accept-encoding": "gzip",
    "os": "android",
    "authorization": f"Bearer {JWT_TOKEN}",
}

# Corrected endpoints from traffic capture
ENDPOINTS = {
    "categories": "/customer_app/api/v2/categories",
    "items": "/customer_app/api/v2/items",  # Products!
    "offers": "/customer_app/api/v2/offers",
    "brands": "/customer_app/api/v2/brands",
    "home": "/customer_app/api/v2/home",
    "hero_banner": "/customer_app/api/v2/hero_banner",
    "cart": "/customer_app/api/v2/cart",
}

def test_endpoint(client, base_url, path, params=None, label=""):
    """Test a single endpoint."""
    url = f"{base_url}{path}"
    print(f"\n=== {label}: {url} ===")
    try:
        resp = client.get(url, params=params, headers=HEADERS)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            preview = json.dumps(data, ensure_ascii=False, indent=2)[:1200]
            print(f"Response: {preview}...")
            return data
        else:
            print(f"Error: {resp.text[:200]}")
    except Exception as e:
        print(f"Exception: {e}")
    return None

def test_api():
    """Test Ben Soliman API endpoints."""
    with httpx.Client(timeout=30.0) as client:

        # Test categories
        categories = test_endpoint(
            client, BASE_URL_1,
            ENDPOINTS["categories"],
            params={"domain_id": 2},
            label="Categories"
        )

        # Get first category ID
        category_id = None
        if categories and "categories" in categories:
            first_cat = categories["categories"][0]
            category_id = first_cat.get("category_Id")
            print(f"\nUsing category: {first_cat.get('Name')} (ID: {category_id})")

        # Test items (products)
        test_endpoint(
            client, BASE_URL_1,
            ENDPOINTS["items"],
            params={"domain_id": 2},
            label="Items (Products)"
        )

        # Test items with category
        if category_id:
            test_endpoint(
                client, BASE_URL_1,
                ENDPOINTS["items"],
                params={"domain_id": 2, "category_id": category_id},
                label=f"Items in category {category_id}"
            )

        # Test offers
        test_endpoint(
            client, BASE_URL_1,
            ENDPOINTS["offers"],
            params={"domain_id": 2},
            label="Offers"
        )

        # Test brands
        test_endpoint(
            client, BASE_URL_1,
            ENDPOINTS["brands"],
            params={"domain_id": 2},
            label="Brands"
        )

        # Test home
        test_endpoint(
            client, BASE_URL_1,
            ENDPOINTS["home"],
            params={"domain_id": 2},
            label="Home"
        )

        # Test hero banner
        test_endpoint(
            client, BASE_URL_1,
            ENDPOINTS["hero_banner"],
            params={"domain_id": 2},
            label="Hero Banner"
        )

if __name__ == "__main__":
    test_api()
