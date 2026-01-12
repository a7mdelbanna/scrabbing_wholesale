"""Base scraper class with common functionality."""
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, Optional
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.utils.http_client import AsyncAPIClient
from src.utils.rate_limiter import RateLimiter, RequestJitter
from src.utils.fingerprint import DeviceFingerprint
from src.utils.exceptions import AuthenticationError
from src.database.repositories.product_repo import ProductRepository, CategoryRepository
from src.database.repositories.price_repo import PriceRepository
from src.models.database import ScrapeJob
from src.models.schemas import ProductCreate, PriceRecordCreate, CategoryCreate
from src.models.enums import SourceApp, JobStatus, JobType, Currency, UnitType
from src.scrapers.auth.token_manager import TokenManager

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Abstract base class for competitor app scrapers.

    Provides common functionality for authentication, rate limiting,
    error handling, and data storage.
    """

    # Subclasses should override these
    SOURCE_APP: SourceApp = None
    BASE_URL: str = ""

    def __init__(self, session: AsyncSession):
        """Initialize the scraper.

        Args:
            session: Database session.
        """
        self.session = session
        self.product_repo = ProductRepository(session)
        self.category_repo = CategoryRepository(session)
        self.price_repo = PriceRepository(session)
        self.token_manager = TokenManager(session)

        # Setup rate limiter and fingerprint
        self.rate_limiter = RateLimiter(
            requests_per_second=settings.requests_per_second,
            burst_size=settings.burst_size,
        )
        self.fingerprint = DeviceFingerprint(
            source_app=self.SOURCE_APP.value if self.SOURCE_APP else "unknown"
        )

        # HTTP client will be initialized in context manager
        self._client: Optional[AsyncAPIClient] = None
        self._current_job: Optional[ScrapeJob] = None

        # Statistics
        self._stats = {
            "products_scraped": 0,
            "products_new": 0,
            "products_updated": 0,
            "errors": 0,
        }

    async def __aenter__(self):
        """Enter async context and initialize HTTP client."""
        self._client = AsyncAPIClient(
            base_url=self.BASE_URL,
            rate_limiter=self.rate_limiter,
            fingerprint=self.fingerprint,
        )
        await self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context and cleanup."""
        if self._client:
            await self._client.__aexit__(exc_type, exc_val, exc_tb)

    # ============== Abstract Methods ==============
    # Subclasses must implement these

    @abstractmethod
    async def authenticate(self) -> bool:
        """Authenticate with the app's API.

        Returns:
            True if authentication successful.
        """
        pass

    @abstractmethod
    async def fetch_categories(self) -> List[Dict[str, Any]]:
        """Fetch all product categories from the API.

        Returns:
            List of category data dictionaries.
        """
        pass

    @abstractmethod
    async def fetch_products(self, category_id: str = None) -> List[Dict[str, Any]]:
        """Fetch products, optionally filtered by category.

        Args:
            category_id: Optional category filter.

        Returns:
            List of product data dictionaries.
        """
        pass

    @abstractmethod
    def parse_product(self, raw_data: Dict[str, Any]) -> ProductCreate:
        """Parse raw API response into ProductCreate schema.

        Args:
            raw_data: Raw product data from API.

        Returns:
            ProductCreate instance.
        """
        pass

    @abstractmethod
    def parse_category(self, raw_data: Dict[str, Any]) -> CategoryCreate:
        """Parse raw API response into CategoryCreate schema.

        Args:
            raw_data: Raw category data from API.

        Returns:
            CategoryCreate instance.
        """
        pass

    # ============== Common Methods ==============

    async def ensure_authenticated(self) -> None:
        """Ensure we have a valid authentication token.

        Raises:
            AuthenticationError: If authentication fails.
        """
        # Check if we have a valid token
        is_valid = await self.token_manager.is_token_valid(self.SOURCE_APP)

        if is_valid:
            # Load token into HTTP client
            token = await self.token_manager.get_access_token(self.SOURCE_APP)
            if token:
                self._client.set_auth_token(token)
                logger.debug(f"Using existing token for {self.SOURCE_APP.value}")
                return

        # Need to authenticate
        logger.info(f"Authenticating with {self.SOURCE_APP.value}")
        success = await self.authenticate()

        if not success:
            raise AuthenticationError(f"Failed to authenticate with {self.SOURCE_APP.value}")

    async def _start_job(self, job_type: JobType) -> ScrapeJob:
        """Start a new scrape job and record it.

        Args:
            job_type: Type of scrape job.

        Returns:
            Created ScrapeJob instance.
        """
        job = ScrapeJob(
            source_app=self.SOURCE_APP.value,
            job_type=job_type.value,
            status=JobStatus.RUNNING.value,
            started_at=datetime.utcnow(),
        )
        self.session.add(job)
        await self.session.flush()

        self._current_job = job
        self._stats = {
            "products_scraped": 0,
            "products_new": 0,
            "products_updated": 0,
            "errors": 0,
        }

        logger.info(f"Started {job_type.value} scrape job #{job.id} for {self.SOURCE_APP.value}")
        return job

    async def _finish_job(self, status: JobStatus, error_details: dict = None) -> None:
        """Finish the current scrape job.

        Args:
            status: Final job status.
            error_details: Optional error information.
        """
        if not self._current_job:
            return

        self._current_job.status = status.value
        self._current_job.completed_at = datetime.utcnow()
        self._current_job.products_scraped = self._stats["products_scraped"]
        self._current_job.products_new = self._stats["products_new"]
        self._current_job.products_updated = self._stats["products_updated"]
        self._current_job.errors_count = self._stats["errors"]
        self._current_job.error_details = error_details

        await self.session.flush()

        logger.info(
            f"Finished scrape job #{self._current_job.id} - "
            f"Status: {status.value}, "
            f"Products: {self._stats['products_scraped']}, "
            f"New: {self._stats['products_new']}, "
            f"Errors: {self._stats['errors']}"
        )

    async def process_product(
        self,
        raw_data: Dict[str, Any],
        price: Decimal,
        original_price: Decimal = None,
        is_available: bool = True,
    ) -> None:
        """Process a single product from API response.

        Args:
            raw_data: Raw product data.
            price: Current price.
            original_price: Original price before discount.
            is_available: Product availability.
        """
        try:
            # Parse product data
            product_data = self.parse_product(raw_data)

            # Upsert product
            product, is_new = await self.product_repo.upsert(product_data)

            # Check if we should record price
            should_record = await self.price_repo.should_record_price(
                product.id, price, is_available
            )

            if should_record:
                # Calculate discount percentage
                discount_pct = None
                if original_price and original_price > price:
                    discount_pct = ((original_price - price) / original_price * 100).quantize(Decimal("0.01"))

                price_record = PriceRecordCreate(
                    product_id=product.id,
                    source_app=self.SOURCE_APP,
                    price=price,
                    original_price=original_price,
                    discount_percentage=discount_pct,
                    currency=Currency.EGP,
                    is_available=is_available,
                )
                await self.price_repo.create(
                    price_record,
                    scrape_job_id=self._current_job.id if self._current_job else None,
                )

            # Update stats
            self._stats["products_scraped"] += 1
            if is_new:
                self._stats["products_new"] += 1
            else:
                self._stats["products_updated"] += 1

        except Exception as e:
            logger.error(f"Error processing product: {e}", exc_info=True)
            self._stats["errors"] += 1

    async def run_full_scrape(self) -> None:
        """Run a full scrape of all products.

        This is the main entry point for scheduled scraping.
        """
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

            # Fetch and process products
            logger.info(f"Fetching products for {self.SOURCE_APP.value}")
            products = await self.fetch_products()

            for product_data in products:
                # Extract price from raw data - subclass should handle this
                price = Decimal(str(product_data.get("price", 0)))
                original_price = None
                if product_data.get("original_price"):
                    original_price = Decimal(str(product_data["original_price"]))

                is_available = product_data.get("is_available", True)

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
