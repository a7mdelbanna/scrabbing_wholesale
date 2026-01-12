"""Scraper for ZAH CODE apps (El Rabie, Gomla Shoaib).

ZAH CODE apps share the same Laravel API structure with different base URLs.
API Discovery completed 2026-01-12 via APK static analysis (baksmali).
"""
import logging
import random
from typing import List, Dict, Any, Optional
from decimal import Decimal

from src.scrapers.base import BaseScraper
from src.models.schemas import ProductCreate, CategoryCreate
from src.models.enums import SourceApp, UnitType
from src.config.settings import settings

logger = logging.getLogger(__name__)


class ZahCodeBaseScraper(BaseScraper):
    """Base scraper for ZAH CODE apps.

    All ZAH CODE apps use the same Laravel API structure:
    - JWT authentication with VERY short token expiry
    - Same endpoints: category/all, products/all, products/category_id, etc.
    - Same data structures for products/categories

    API Documentation: docs/zahcode_api.md
    """

    # Subclasses must override these
    SOURCE_APP: SourceApp = None
    BASE_URL: str = ""

    # API endpoints (same for all ZAH CODE apps)
    ENDPOINTS = {
        "register": "auth/register",
        "login": "auth/login",
        "check_mobile": "auth/check-mobile",
        "me": "auth/me",
        "categories": "category/all",
        "subcategories": "subcategory/all",
        "products_all": "products/all",
        "products_by_category": "products/category_id",
        "best_sellers": "products/best_seller",
        "offers": "products/offers",
        "sliders": "slider/all",
    }

    # HTTP method for product endpoints (some ZAH CODE apps use POST instead of GET)
    PRODUCTS_HTTP_METHOD = "GET"

    # Registration data for creating scraper accounts
    _registration_data = {
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._current_token: Optional[str] = None

    async def _get_fresh_token(self) -> Optional[str]:
        """Get a fresh authentication token.

        ZAH CODE tokens expire very quickly, so we need to get a fresh
        token before each API call or batch of calls.

        Returns:
            Fresh JWT token or None if authentication fails.
        """
        # Try to login with stored credentials first
        credential = await self.token_manager.get_credential(self.SOURCE_APP)

        if credential:
            password = await self.token_manager.get_password(self.SOURCE_APP)
            try:
                response = await self._client.post(
                    self.ENDPOINTS["login"],
                    form_data={
                        "mobile": credential.username,
                        "password": password,
                    },
                )

                if response and "access_token" in response:
                    return response["access_token"]

            except Exception as e:
                logger.warning(f"Login failed, will try to register: {e}")

        # If login fails, try to register a new account
        return await self._register_new_account()

    async def _register_new_account(self) -> Optional[str]:
        """Register a new scraper account.

        Returns:
            Fresh JWT token or None if registration fails.
        """
        # Generate unique phone and email
        phone = f"010{random.randint(10000000, 99999999)}"
        email = f"scraper{random.randint(1000, 9999)}@scraper.local"

        try:
            reg_data = {
                **self._registration_data,
                "mobile": phone,
                "email": email,
            }

            response = await self._client.post(
                self.ENDPOINTS["register"],
                form_data=reg_data,
            )

            if response and "access_token" in response:
                # Store the new credentials for future use
                await self.token_manager.store_credential(
                    source_app=self.SOURCE_APP,
                    username=phone,
                    password=self._registration_data["password"],
                )

                logger.info(f"Registered new account for {self.SOURCE_APP.value}: {phone}")
                return response["access_token"]

            logger.error(f"Registration failed: {response}")
            return None

        except Exception as e:
            logger.error(f"Registration failed: {e}")
            return None

    async def authenticate(self) -> bool:
        """Authenticate with ZAH CODE API.

        Due to extremely short token expiry, this gets a fresh token
        and stores it for immediate use.

        Returns:
            True if authentication successful.
        """
        token = await self._get_fresh_token()

        if token:
            self._current_token = token
            self._client.set_auth_token(token)
            logger.info(f"Authenticated with {self.SOURCE_APP.value}")
            return True

        logger.error(f"Failed to authenticate with {self.SOURCE_APP.value}")
        return False

    async def _ensure_fresh_token(self) -> bool:
        """Ensure we have a fresh token before making API calls.

        ZAH CODE tokens expire very quickly, so we refresh before each batch.

        Returns:
            True if token is available.
        """
        token = await self._get_fresh_token()
        if token:
            self._current_token = token
            self._client.set_auth_token(token)
            return True
        return False

    async def fetch_categories(self) -> List[Dict[str, Any]]:
        """Fetch all categories from ZAH CODE API.

        Returns:
            List of category data dictionaries.
        """
        if not await self._ensure_fresh_token():
            return []

        try:
            response = await self._client.get(self.ENDPOINTS["categories"])

            if isinstance(response, list):
                logger.info(f"Fetched {len(response)} categories from {self.SOURCE_APP.value}")
                return response

            logger.warning(f"Unexpected category response: {response}")
            return []

        except Exception as e:
            logger.error(f"Failed to fetch categories: {e}")
            return []

    async def fetch_subcategories(self) -> List[Dict[str, Any]]:
        """Fetch all subcategories.

        Returns:
            List of subcategory data dictionaries.
        """
        if not await self._ensure_fresh_token():
            return []

        try:
            response = await self._client.get(self.ENDPOINTS["subcategories"])

            if isinstance(response, list):
                logger.info(f"Fetched {len(response)} subcategories from {self.SOURCE_APP.value}")
                return response

            return []

        except Exception as e:
            logger.error(f"Failed to fetch subcategories: {e}")
            return []

    async def fetch_products(self, category_id: str = None) -> List[Dict[str, Any]]:
        """Fetch products, optionally by category.

        The products/all endpoint returns limited results (10 items).
        For full catalog, use fetch_products_by_category for each category.

        Note: Some ZAH CODE apps (like Gomla Shoaib) require POST method
        instead of GET for product endpoints. This is controlled by
        PRODUCTS_HTTP_METHOD class variable.

        Args:
            category_id: Optional category ID to filter by.

        Returns:
            List of product data dictionaries.
        """
        if not await self._ensure_fresh_token():
            return []

        try:
            if category_id:
                endpoint = self.ENDPOINTS["products_by_category"]
                params = {"category_id": category_id}
                if self.PRODUCTS_HTTP_METHOD == "POST":
                    response = await self._client.post(endpoint, params=params)
                else:
                    response = await self._client.get(endpoint, params=params)
            else:
                endpoint = self.ENDPOINTS["products_all"]
                if self.PRODUCTS_HTTP_METHOD == "POST":
                    response = await self._client.post(endpoint)
                else:
                    response = await self._client.get(endpoint)

            if isinstance(response, list):
                logger.info(f"Fetched {len(response)} products from {self.SOURCE_APP.value}")
                return response

            logger.warning(f"Unexpected products response: {response}")
            return []

        except Exception as e:
            logger.error(f"Failed to fetch products: {e}")
            return []

    async def fetch_all_products(self) -> List[Dict[str, Any]]:
        """Fetch all products by iterating through categories.

        The products/all endpoint returns limited results, so we need
        to fetch by category to get the full catalog.

        Returns:
            List of all product data dictionaries.
        """
        all_products = []
        seen_ids = set()

        # Get all categories
        categories = await self.fetch_categories()

        for category in categories:
            category_id = category.get("id")
            if not category_id:
                continue

            # Fetch products for this category (will get fresh token)
            products = await self.fetch_products(category_id=str(category_id))

            for product in products:
                product_id = product.get("id")
                if product_id and product_id not in seen_ids:
                    seen_ids.add(product_id)
                    # Add category info to product
                    product["category_id"] = category_id
                    product["category_name"] = category.get("name")
                    all_products.append(product)

        logger.info(f"Fetched total of {len(all_products)} unique products")
        return all_products

    async def fetch_offers(self) -> List[Dict[str, Any]]:
        """Fetch products with active offers.

        Returns:
            List of offer product data.
        """
        if not await self._ensure_fresh_token():
            return []

        try:
            endpoint = self.ENDPOINTS["offers"]
            if self.PRODUCTS_HTTP_METHOD == "POST":
                response = await self._client.post(endpoint)
            else:
                response = await self._client.get(endpoint)

            if isinstance(response, list):
                logger.info(f"Fetched {len(response)} offers from {self.SOURCE_APP.value}")
                return response

            return []

        except Exception as e:
            logger.error(f"Failed to fetch offers: {e}")
            return []

    async def fetch_best_sellers(self) -> List[Dict[str, Any]]:
        """Fetch best selling products.

        Returns:
            List of best seller product data.
        """
        if not await self._ensure_fresh_token():
            return []

        try:
            response = await self._client.get(self.ENDPOINTS["best_sellers"])

            if isinstance(response, list):
                logger.info(f"Fetched {len(response)} best sellers from {self.SOURCE_APP.value}")
                return response

            return []

        except Exception as e:
            logger.error(f"Failed to fetch best sellers: {e}")
            return []

    def parse_product(self, raw_data: Dict[str, Any]) -> ProductCreate:
        """Parse ZAH CODE product response into ProductCreate.

        API Response fields:
        - id: Product ID
        - name: Product name (Arabic)
        - description: Product description (may contain HTML)
        - image: Full image URL
        - stock: Stock quantity
        - total_allowed_quantity: Max order quantity
        - variants: List of unit variants with prices

        Variant fields:
        - id: Variant ID
        - price: Original price
        - discounted_price: Current selling price
        - unit: Unit name (Arabic: علبة, باكت, كرتونة)
        - measurement: Unit measurement
        - offer: Has offer (0/1)
        - offer_quantity: Min quantity for offer

        Args:
            raw_data: Raw product data from API.

        Returns:
            ProductCreate instance.
        """
        # Extract primary variant (first one)
        variants = raw_data.get("variants", [])
        primary_variant = variants[0] if variants else {}

        # Get prices from primary variant
        price = primary_variant.get("discounted_price") or primary_variant.get("price")
        original_price = primary_variant.get("price")
        unit_name = primary_variant.get("unit", "piece")

        # Calculate discount if prices differ
        discount_pct = None
        if price and original_price and float(original_price) > float(price):
            discount_pct = round((1 - float(price) / float(original_price)) * 100, 2)

        # Check availability
        stock = raw_data.get("stock", 0)
        is_available = stock > 0

        # Clean description (remove HTML tags)
        description = raw_data.get("description", "")
        if description:
            import re
            description = re.sub(r'<[^>]+>', '', description).strip()

        return ProductCreate(
            source_app=self.SOURCE_APP,
            external_id=str(raw_data.get("id", "")),
            name=raw_data.get("name", ""),
            name_ar=raw_data.get("name"),  # API returns Arabic
            description=description,
            description_ar=description,
            category_external_id=str(raw_data.get("category_id")) if raw_data.get("category_id") else None,
            brand=None,  # Not available in API
            sku=str(raw_data.get("id")),
            barcode=None,  # Not available in API
            image_url=raw_data.get("image"),
            unit_type=self._parse_unit(unit_name),
            min_order_quantity=1,
            max_order_quantity=raw_data.get("total_allowed_quantity"),
            current_price=Decimal(str(price)) if price else None,
            original_price=Decimal(str(original_price)) if original_price else None,
            discount_percentage=discount_pct,
            is_available=is_available,
            extra_data={
                "stock": stock,
                "total_allowed_quantity": raw_data.get("total_allowed_quantity"),
                "category_name": raw_data.get("category_name"),
                "variants": variants,  # Store all variants for multi-unit pricing
            },
        )

    def parse_category(self, raw_data: Dict[str, Any]) -> CategoryCreate:
        """Parse ZAH CODE category response into CategoryCreate.

        API Response fields:
        - id: Category ID
        - name: Category name (Arabic)
        - image: Full image URL
        - created_at: Creation timestamp
        - updated_at: Update timestamp

        Args:
            raw_data: Raw category data from API.

        Returns:
            CategoryCreate instance.
        """
        return CategoryCreate(
            source_app=self.SOURCE_APP,
            external_id=str(raw_data.get("id", "")),
            name=raw_data.get("name", ""),
            name_ar=raw_data.get("name"),  # API returns Arabic
            parent_external_id=None,  # No parent info in main categories
            image_url=raw_data.get("image"),
            sort_order=0,  # No sort info in API
        )

    def _parse_unit(self, unit_str: str) -> UnitType:
        """Parse Arabic unit string to UnitType enum.

        Args:
            unit_str: Unit string from API (Arabic).

        Returns:
            UnitType enum value.
        """
        unit_mapping = {
            # Arabic units
            "قطعة": UnitType.PIECE,
            "وحدة": UnitType.PIECE,
            "علبة": UnitType.BOX,
            "باكت": UnitType.PACK,
            "عبوة": UnitType.PACK,
            "كرتونة": UnitType.CARTON,
            "كرتون": UnitType.CARTON,
            "دستة": UnitType.CARTON,
            "كيلو": UnitType.KG,
            "جرام": UnitType.GRAM,
            "لتر": UnitType.LITER,
            # English units
            "piece": UnitType.PIECE,
            "pcs": UnitType.PIECE,
            "unit": UnitType.PIECE,
            "box": UnitType.BOX,
            "pack": UnitType.PACK,
            "carton": UnitType.CARTON,
            "kg": UnitType.KG,
            "gram": UnitType.GRAM,
            "liter": UnitType.LITER,
            "ml": UnitType.ML,
        }

        if unit_str:
            return unit_mapping.get(unit_str.lower(), UnitType.PIECE)
        return UnitType.PIECE

    async def run_full_scrape(self) -> None:
        """Run a full scrape of all products.

        Overrides base class to use fetch_all_products which iterates
        through categories for complete coverage.
        """
        from src.models.enums import JobType, JobStatus
        from src.utils.rate_limiter import RequestJitter

        await self._start_job(JobType.FULL)

        try:
            # Ensure we're authenticated
            await self.ensure_authenticated()

            # Add startup delay
            await RequestJitter.wait_session_start()

            # Fetch and process categories
            logger.info(f"Fetching categories for {self.SOURCE_APP.value}")
            categories = await self.fetch_categories()

            for cat_data in categories:
                category_schema = self.parse_category(cat_data)
                await self.category_repo.upsert(category_schema)

            logger.info(f"Processed {len(categories)} categories")

            # Fetch and process all products (via categories)
            logger.info(f"Fetching all products for {self.SOURCE_APP.value}")
            products = await self.fetch_all_products()

            for product_data in products:
                # Get prices from variants
                variants = product_data.get("variants", [])
                if variants:
                    primary = variants[0]
                    price = Decimal(str(primary.get("discounted_price") or primary.get("price", 0)))
                    original_price = Decimal(str(primary.get("price", 0))) if primary.get("price") else None
                else:
                    price = Decimal("0")
                    original_price = None

                is_available = product_data.get("stock", 0) > 0

                await self.process_product(
                    product_data, price, original_price, is_available
                )

            await self._finish_job(JobStatus.COMPLETED)

        except Exception as e:
            logger.error(f"Scrape job failed: {e}", exc_info=True)
            await self._finish_job(
                JobStatus.FAILED,
                error_details={"error": str(e), "type": type(e).__name__},
            )
            raise


class ElRabieScraper(ZahCodeBaseScraper):
    """Scraper for El Rabie (شركة الربيع) wholesale app.

    Package: com.zahcode.white_shop
    API: https://gomletalrabia.zahcode.online/api/
    """

    SOURCE_APP = SourceApp.EL_RABIE
    BASE_URL = "https://gomletalrabia.zahcode.online/api/"


class GomlaShoaibScraper(ZahCodeBaseScraper):
    """Scraper for Gomla Shoaib (جملة شعيب) wholesale app.

    Package: com.zahcode.gomlet_shoaib
    API: https://gomletshoaib.zahcode.online/api/

    Note: This app uses POST method for product endpoints instead of GET.
    """

    SOURCE_APP = SourceApp.GOMLA_SHOAIB
    BASE_URL = "https://gomletshoaib.zahcode.online/api/"
    PRODUCTS_HTTP_METHOD = "POST"  # Gomla Shoaib requires POST for products
