"""Scraper for Ben Soliman (بن سليمان) app.

API Discovery completed 2026-01-12 via tcpdump traffic capture.
"""
import logging
from typing import List, Dict, Any, Optional
from decimal import Decimal

from src.scrapers.base import BaseScraper
from src.models.schemas import ProductCreate, CategoryCreate
from src.models.enums import SourceApp, UnitType
from src.config.settings import settings

logger = logging.getLogger(__name__)


class BenSolimanScraper(BaseScraper):
    """Scraper for Ben Soliman wholesale app.

    API Documentation: docs/ben_soliman_api.md
    """

    SOURCE_APP = SourceApp.BEN_SOLIMAN

    # Discovered API servers (load balanced)
    BASE_URLS = [
        "http://41.65.168.38:8001",
        "http://37.148.206.212:5005",
    ]
    BASE_URL = BASE_URLS[0]  # Primary server

    # Default domain_id for Cairo/Giza region
    DEFAULT_DOMAIN_ID = 2

    # API endpoints verified via testing
    ENDPOINTS = {
        "login": "/customer_app/api/v2/login",
        "categories": "/customer_app/api/v2/categories",
        "items": "/customer_app/api/v2/items",  # Products endpoint
        "brands": "/customer_app/api/v2/brands",
        "offers": "/customer_app/api/v2/offers",
        "home": "/customer_app/api/v2/home",
        "hero_banner": "/customer_app/api/v2/hero_banner",
        "cart": "/customer_app/api/v2/cart",
        "domains": "/customer_app/api/v2/domains",  # On secondary server
    }

    # Required headers for Ben Soliman API
    DEFAULT_HEADERS = {
        "user-agent": "Dart/3.9 (dart:io)",
        "accept-language": "ar",
        "accept-encoding": "gzip",
        "os": "android",
    }

    async def authenticate(self) -> bool:
        """Authenticate with Ben Soliman API.

        Login endpoint: POST /customer_app/api/v2/login?is_reset_password=false
        Request body: {"Mob": "phone", "Password": "password"}

        Note: The API returns JWT tokens with very long expiry (~10 years).

        Returns:
            True if authentication successful.
        """
        credential = await self.token_manager.get_credential(self.SOURCE_APP)

        if not credential:
            logger.error("No credentials stored for Ben Soliman")
            return False

        # Check if we have a valid cached token
        cached_token = await self.token_manager.get_access_token(self.SOURCE_APP)
        if cached_token:
            self._client.set_auth_token(cached_token)
            for key, value in self.DEFAULT_HEADERS.items():
                self._client.set_header(key, value)
            logger.info("Using cached authentication token for Ben Soliman")
            return True

        # Perform login
        password = await self.token_manager.get_password(self.SOURCE_APP)

        try:
            response = await self._client.post(
                f"{self.ENDPOINTS['login']}?is_reset_password=false",
                json_data={
                    "Mob": credential.username,
                    "Password": password,
                },
                headers=self.DEFAULT_HEADERS,
            )

            # Extract token from response
            access_token = response.get("token") or response.get("access_token")

            if not access_token and isinstance(response, dict):
                # Token might be in nested structure
                access_token = response.get("data", {}).get("token")

            if access_token:
                await self.token_manager.store_tokens(
                    source_app=self.SOURCE_APP,
                    access_token=access_token,
                    refresh_token=None,  # No refresh token, main token is long-lived
                    expires_in_seconds=315360000,  # ~10 years
                )
                self._client.set_auth_token(access_token)
                for key, value in self.DEFAULT_HEADERS.items():
                    self._client.set_header(key, value)
                logger.info("Successfully authenticated with Ben Soliman")
                return True

            logger.error(f"No token in authentication response: {response}")
            return False

        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False

    async def fetch_domains(self) -> List[Dict[str, Any]]:
        """Fetch available domains (regions/areas).

        Returns:
            List of domain data.
        """
        try:
            response = await self._client.get(
                self.ENDPOINTS["domains"],
                headers=self.DEFAULT_HEADERS,
            )
            return response if isinstance(response, list) else response.get("data", [])
        except Exception as e:
            logger.error(f"Failed to fetch domains: {e}")
            return []

    async def fetch_categories(self, domain_id: int = None) -> List[Dict[str, Any]]:
        """Fetch all categories from Ben Soliman.

        Args:
            domain_id: Domain/region ID (default: Cairo/Giza = 2)

        Returns:
            List of category data dictionaries.
        """
        categories = []
        domain_id = domain_id or self.DEFAULT_DOMAIN_ID

        try:
            response = await self._client.get(
                self.ENDPOINTS["categories"],
                params={"domain_id": domain_id},
                headers=self.DEFAULT_HEADERS,
            )

            # Response format: {"categories": [...]}
            raw_categories = response.get("categories", []) if isinstance(response, dict) else response

            if isinstance(raw_categories, list):
                categories = raw_categories

            logger.info(f"Fetched {len(categories)} categories from Ben Soliman")

        except Exception as e:
            logger.error(f"Failed to fetch categories: {e}")

        return categories

    async def fetch_section(self, section_id: int, domain_id: int = None) -> Dict[str, Any]:
        """Fetch section/category details.

        Args:
            section_id: Section ID to fetch
            domain_id: Domain/region ID

        Returns:
            Section data dictionary.
        """
        domain_id = domain_id or self.DEFAULT_DOMAIN_ID

        try:
            response = await self._client.get(
                self.ENDPOINTS["section"],
                params={
                    "domain_id": domain_id,
                    "section_id": section_id,
                },
                headers=self.DEFAULT_HEADERS,
            )
            return response
        except Exception as e:
            logger.error(f"Failed to fetch section {section_id}: {e}")
            return {}

    async def fetch_products(
        self,
        category_id: int = None,
        domain_id: int = None,
    ) -> List[Dict[str, Any]]:
        """Fetch products (items) from Ben Soliman.

        Args:
            category_id: Category ID to filter by (optional)
            domain_id: Domain/region ID

        Returns:
            List of product data dictionaries.
        """
        products = []
        domain_id = domain_id or self.DEFAULT_DOMAIN_ID

        try:
            params = {"domain_id": domain_id}
            if category_id:
                params["category_id"] = category_id

            response = await self._client.get(
                self.ENDPOINTS["items"],
                params=params,
                headers=self.DEFAULT_HEADERS,
            )

            # Response format: {"data": [...]}
            raw_products = response.get("data", []) if isinstance(response, dict) else response

            if isinstance(raw_products, list):
                products = raw_products

            logger.info(f"Fetched {len(products)} products from Ben Soliman")

        except Exception as e:
            logger.error(f"Failed to fetch products: {e}")

        return products

    async def fetch_all_products(self, domain_id: int = None) -> List[Dict[str, Any]]:
        """Fetch all products from all categories.

        Args:
            domain_id: Domain/region ID

        Returns:
            List of all product data dictionaries.
        """
        all_products = []
        domain_id = domain_id or self.DEFAULT_DOMAIN_ID

        # First get all categories
        categories = await self.fetch_categories(domain_id)

        for category in categories:
            category_id = category.get("category_Id")
            if category_id:
                products = await self.fetch_products(
                    category_id=category_id,
                    domain_id=domain_id,
                )
                all_products.extend(products)

        logger.info(f"Fetched total of {len(all_products)} products from all categories")
        return all_products

    async def fetch_brands(self, domain_id: int = None) -> List[Dict[str, Any]]:
        """Fetch all brands from Ben Soliman.

        Args:
            domain_id: Domain/region ID

        Returns:
            List of brand data dictionaries.
        """
        domain_id = domain_id or self.DEFAULT_DOMAIN_ID

        try:
            response = await self._client.get(
                self.ENDPOINTS["brands"],
                params={"domain_id": domain_id},
                headers=self.DEFAULT_HEADERS,
            )
            # Response format: {"Brands": [...]}
            brands = response.get("Brands", []) if isinstance(response, dict) else response
            logger.info(f"Fetched {len(brands)} brands from Ben Soliman")
            return brands
        except Exception as e:
            logger.error(f"Failed to fetch brands: {e}")
            return []

    async def fetch_offers(self, domain_id: int = None) -> List[Dict[str, Any]]:
        """Fetch active offers and promotions.

        Args:
            domain_id: Domain/region ID

        Returns:
            List of offer data dictionaries.
        """
        domain_id = domain_id or self.DEFAULT_DOMAIN_ID

        try:
            response = await self._client.get(
                self.ENDPOINTS["offers"],
                params={"domain_id": domain_id},
                headers=self.DEFAULT_HEADERS,
            )
            offers = response if isinstance(response, list) else response.get("data", response.get("Offers", []))
            logger.info(f"Fetched {len(offers)} offers from Ben Soliman")
            return offers
        except Exception as e:
            logger.error(f"Failed to fetch offers: {e}")
            return []

    async def fetch_home_data(self, domain_id: int = None) -> Dict[str, Any]:
        """Fetch home page data with sections.

        Args:
            domain_id: Domain/region ID

        Returns:
            Home data dictionary with sections.
        """
        domain_id = domain_id or self.DEFAULT_DOMAIN_ID

        try:
            response = await self._client.get(
                self.ENDPOINTS["home"],
                params={"domain_id": domain_id},
                headers=self.DEFAULT_HEADERS,
            )
            return response
        except Exception as e:
            logger.error(f"Failed to fetch home data: {e}")
            return {}

    def parse_product(self, raw_data: Dict[str, Any]) -> ProductCreate:
        """Parse Ben Soliman product response into ProductCreate.

        API Response fields:
        - ItemCode: Product ID
        - Name: Product name (Arabic)
        - SellPrice: Current price
        - ItemPrice: Original price
        - Balance: Stock quantity
        - ImageName: Image filename
        - CategoryCode: Category ID
        - BrandId: Brand ID
        - BarCode: Barcode
        - Description: Product description
        - u_codes: Unit information

        Args:
            raw_data: Raw product data from API.

        Returns:
            ProductCreate instance.
        """
        # Extract price info
        sell_price = raw_data.get("SellPrice") or raw_data.get("ItemPrice")
        item_price = raw_data.get("ItemPrice")

        # Calculate discount if prices differ
        discount_pct = None
        if sell_price and item_price and float(item_price) > float(sell_price):
            discount_pct = round((1 - float(sell_price) / float(item_price)) * 100, 2)

        # Build image URL
        image_name = raw_data.get("ImageName")
        image_url = f"http://37.148.206.212/Icons/{image_name}" if image_name else None

        # Get unit info from u_codes
        unit_name = "piece"
        if raw_data.get("u_codes") and len(raw_data["u_codes"]) > 0:
            unit_name = raw_data["u_codes"][0].get("U_Name", "piece")

        return ProductCreate(
            source_app=self.SOURCE_APP,
            external_id=str(raw_data.get("ItemCode", "")),
            name=raw_data.get("Name", ""),
            name_ar=raw_data.get("Name"),  # API returns Arabic
            description=raw_data.get("Description"),
            description_ar=raw_data.get("Description"),
            category_external_id=str(raw_data.get("CategoryCode")) if raw_data.get("CategoryCode") else None,
            brand=str(raw_data.get("BrandId")) if raw_data.get("BrandId") else None,
            sku=str(raw_data.get("ItemCode")),
            barcode=raw_data.get("BarCode"),
            image_url=image_url,
            unit_type=self._parse_unit(unit_name),
            min_order_quantity=raw_data.get("MinimumQuantity", 1),
            current_price=Decimal(str(sell_price)) if sell_price else None,
            original_price=Decimal(str(item_price)) if item_price else None,
            discount_percentage=discount_pct,
            is_available=raw_data.get("Balance", 0) > 0,
            extra_data={
                "balance": raw_data.get("Balance"),
                "sales_limit": raw_data.get("SalesLimit"),
                "coins": raw_data.get("Coins"),
                "stars": raw_data.get("Stars"),
                "item_points": raw_data.get("ItemPoints"),
                "is_favorite": raw_data.get("IsFav"),
                "offers": raw_data.get("Offers", []),
                "u_codes": raw_data.get("u_codes", []),
            },
        )

    def parse_category(self, raw_data: Dict[str, Any]) -> CategoryCreate:
        """Parse Ben Soliman category response into CategoryCreate.

        API Response fields:
        - category_Id: Category ID
        - Name: Category name (Arabic)
        - ImageName: Image filename
        - IsSpecial: Special category flag
        - Banners: Associated banner ads

        Args:
            raw_data: Raw category data from API.

        Returns:
            CategoryCreate instance.
        """
        # Build image URL
        image_name = raw_data.get("ImageName")
        image_url = f"http://37.148.206.212/Icons/{image_name}" if image_name else None

        return CategoryCreate(
            source_app=self.SOURCE_APP,
            external_id=str(raw_data.get("category_Id", "")),
            name=raw_data.get("Name", ""),
            name_ar=raw_data.get("Name"),  # API returns Arabic
            parent_external_id=None,  # No parent info in API
            image_url=image_url,
            sort_order=0,  # No sort info in API
        )

    def _parse_unit(self, unit_str: str) -> UnitType:
        """Parse unit string to UnitType enum.

        Args:
            unit_str: Unit string from API.

        Returns:
            UnitType enum value.
        """
        unit_mapping = {
            "piece": UnitType.PIECE,
            "pcs": UnitType.PIECE,
            "unit": UnitType.PIECE,
            "قطعة": UnitType.PIECE,
            "kg": UnitType.KG,
            "kilo": UnitType.KG,
            "كيلو": UnitType.KG,
            "gram": UnitType.GRAM,
            "g": UnitType.GRAM,
            "جرام": UnitType.GRAM,
            "liter": UnitType.LITER,
            "l": UnitType.LITER,
            "لتر": UnitType.LITER,
            "ml": UnitType.ML,
            "pack": UnitType.PACK,
            "عبوة": UnitType.PACK,
            "box": UnitType.BOX,
            "علبة": UnitType.BOX,
            "carton": UnitType.CARTON,
            "كرتونة": UnitType.CARTON,
        }

        if unit_str:
            return unit_mapping.get(unit_str.lower(), UnitType.PIECE)
        return UnitType.PIECE
