"""Price record repository for database operations."""
from datetime import datetime, timedelta
from typing import Optional, List
from decimal import Decimal
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import PriceRecord, Product
from src.models.schemas import PriceRecordCreate
from src.models.enums import SourceApp


class PriceRepository:
    """Repository for price record database operations."""

    def __init__(self, session: AsyncSession):
        """Initialize repository with database session.

        Args:
            session: AsyncSession instance.
        """
        self.session = session

    async def create(
        self, price_data: PriceRecordCreate, scrape_job_id: int = None
    ) -> PriceRecord:
        """Create a new price record.

        Args:
            price_data: Price record data.
            scrape_job_id: Optional scrape job ID.

        Returns:
            Created price record.
        """
        price_record = PriceRecord(
            product_id=price_data.product_id,
            source_app=price_data.source_app.value,
            price=price_data.price,
            original_price=price_data.original_price,
            discount_percentage=price_data.discount_percentage,
            currency=price_data.currency.value,
            is_available=price_data.is_available,
            stock_status=price_data.stock_status.value if price_data.stock_status else None,
            scrape_job_id=scrape_job_id,
        )
        self.session.add(price_record)
        await self.session.flush()
        return price_record

    async def get_latest_for_product(self, product_id: int) -> Optional[PriceRecord]:
        """Get the most recent price record for a product.

        Args:
            product_id: Product ID.

        Returns:
            Latest price record or None.
        """
        result = await self.session.execute(
            select(PriceRecord)
            .where(PriceRecord.product_id == product_id)
            .order_by(PriceRecord.recorded_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_price_history(
        self,
        product_id: int,
        days: int = 30,
        limit: int = 100,
    ) -> List[PriceRecord]:
        """Get price history for a product.

        Args:
            product_id: Product ID.
            days: Number of days of history.
            limit: Maximum number of records.

        Returns:
            List of price records ordered by date descending.
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        result = await self.session.execute(
            select(PriceRecord)
            .where(
                PriceRecord.product_id == product_id,
                PriceRecord.recorded_at >= cutoff,
            )
            .order_by(PriceRecord.recorded_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def should_record_price(
        self,
        product_id: int,
        new_price: Decimal,
        is_available: bool,
    ) -> bool:
        """Check if a new price record should be created.

        Only create a new record if price or availability changed.

        Args:
            product_id: Product ID.
            new_price: New price value.
            is_available: New availability status.

        Returns:
            True if a new record should be created.
        """
        latest = await self.get_latest_for_product(product_id)

        if latest is None:
            return True

        # Record if price changed
        if latest.price != new_price:
            return True

        # Record if availability changed
        if latest.is_available != is_available:
            return True

        return False

    async def get_price_comparison(
        self, barcode: str
    ) -> dict:
        """Get price comparison across apps for a product barcode.

        Args:
            barcode: Product barcode.

        Returns:
            Dictionary with prices from each app.
        """
        # Get products with this barcode
        products_result = await self.session.execute(
            select(Product).where(Product.barcode == barcode)
        )
        products = list(products_result.scalars().all())

        comparison = {
            "barcode": barcode,
            "tager_elsaada": None,
            "ben_soliman": None,
        }

        for product in products:
            latest = await self.get_latest_for_product(product.id)
            if latest:
                if product.source_app == SourceApp.TAGER_ELSAADA.value:
                    comparison["tager_elsaada"] = {
                        "product_id": product.id,
                        "name": product.name,
                        "price": float(latest.price),
                        "is_available": latest.is_available,
                    }
                elif product.source_app == SourceApp.BEN_SOLIMAN.value:
                    comparison["ben_soliman"] = {
                        "product_id": product.id,
                        "name": product.name,
                        "price": float(latest.price),
                        "is_available": latest.is_available,
                    }

        return comparison

    async def cleanup_old_records(self, days: int = 90) -> int:
        """Delete price records older than specified days.

        Args:
            days: Age threshold in days.

        Returns:
            Number of records deleted.
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        result = await self.session.execute(
            delete(PriceRecord).where(PriceRecord.recorded_at < cutoff)
        )
        return result.rowcount

    async def get_daily_averages(
        self,
        product_id: int,
        days: int = 30,
    ) -> List[dict]:
        """Get daily average prices for a product.

        Args:
            product_id: Product ID.
            days: Number of days.

        Returns:
            List of daily averages with date and average price.
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        result = await self.session.execute(
            select(
                func.date(PriceRecord.recorded_at).label("date"),
                func.avg(PriceRecord.price).label("avg_price"),
                func.min(PriceRecord.price).label("min_price"),
                func.max(PriceRecord.price).label("max_price"),
            )
            .where(
                PriceRecord.product_id == product_id,
                PriceRecord.recorded_at >= cutoff,
            )
            .group_by(func.date(PriceRecord.recorded_at))
            .order_by(func.date(PriceRecord.recorded_at))
        )

        return [
            {
                "date": str(row.date),
                "avg_price": float(row.avg_price),
                "min_price": float(row.min_price),
                "max_price": float(row.max_price),
            }
            for row in result.all()
        ]
