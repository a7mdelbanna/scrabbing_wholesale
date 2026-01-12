"""Product repository for database operations."""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import Product, Category
from src.models.schemas import ProductCreate, CategoryCreate
from src.models.enums import SourceApp


class ProductRepository:
    """Repository for product database operations."""

    def __init__(self, session: AsyncSession):
        """Initialize repository with database session.

        Args:
            session: AsyncSession instance.
        """
        self.session = session

    async def get_by_external_id(
        self, source_app: SourceApp, external_id: str
    ) -> Optional[Product]:
        """Get product by source app and external ID.

        Args:
            source_app: Source application.
            external_id: External product ID.

        Returns:
            Product or None if not found.
        """
        result = await self.session.execute(
            select(Product).where(
                Product.source_app == source_app.value,
                Product.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_barcode(self, barcode: str) -> List[Product]:
        """Get all products with a specific barcode.

        Args:
            barcode: Product barcode.

        Returns:
            List of products with matching barcode.
        """
        result = await self.session.execute(
            select(Product).where(Product.barcode == barcode)
        )
        return list(result.scalars().all())

    async def create(self, product_data: ProductCreate) -> Product:
        """Create a new product.

        Args:
            product_data: Product creation data.

        Returns:
            Created product.
        """
        product = Product(
            source_app=product_data.source_app.value,
            external_id=product_data.external_id,
            name=product_data.name,
            name_ar=product_data.name_ar,
            description=product_data.description,
            description_ar=product_data.description_ar,
            brand=product_data.brand,
            sku=product_data.sku,
            barcode=product_data.barcode,
            image_url=product_data.image_url,
            additional_images=product_data.additional_images,
            unit_type=product_data.unit_type.value,
            unit_value=product_data.unit_value,
            min_order_quantity=product_data.min_order_quantity,
            extra_data=product_data.extra_data,
        )
        self.session.add(product)
        await self.session.flush()
        return product

    async def update_product(
        self, product: Product, product_data: ProductCreate
    ) -> Product:
        """Update an existing product.

        Args:
            product: Existing product to update.
            product_data: New product data.

        Returns:
            Updated product.
        """
        product.name = product_data.name
        product.name_ar = product_data.name_ar
        product.description = product_data.description
        product.description_ar = product_data.description_ar
        product.brand = product_data.brand
        product.sku = product_data.sku
        product.barcode = product_data.barcode
        product.image_url = product_data.image_url
        product.additional_images = product_data.additional_images
        product.unit_type = product_data.unit_type.value
        product.unit_value = product_data.unit_value
        product.min_order_quantity = product_data.min_order_quantity
        product.extra_data = product_data.extra_data
        product.last_seen_at = datetime.utcnow()

        await self.session.flush()
        return product

    async def upsert(self, product_data: ProductCreate) -> tuple[Product, bool]:
        """Create or update a product.

        Args:
            product_data: Product data.

        Returns:
            Tuple of (product, is_new).
        """
        existing = await self.get_by_external_id(
            product_data.source_app, product_data.external_id
        )

        if existing:
            product = await self.update_product(existing, product_data)
            return product, False
        else:
            product = await self.create(product_data)
            return product, True

    async def get_all_by_source(
        self, source_app: SourceApp, limit: int = 1000, offset: int = 0
    ) -> List[Product]:
        """Get all products from a source app.

        Args:
            source_app: Source application.
            limit: Maximum number of products.
            offset: Number of products to skip.

        Returns:
            List of products.
        """
        result = await self.session.execute(
            select(Product)
            .where(Product.source_app == source_app.value)
            .order_by(Product.id)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def mark_inactive(
        self, source_app: SourceApp, external_ids: List[str]
    ) -> int:
        """Mark products as inactive if not in the provided list.

        Args:
            source_app: Source application.
            external_ids: List of active external IDs.

        Returns:
            Number of products marked inactive.
        """
        result = await self.session.execute(
            update(Product)
            .where(
                Product.source_app == source_app.value,
                Product.external_id.notin_(external_ids),
                Product.is_active == True,
            )
            .values(is_active=False)
        )
        return result.rowcount


class CategoryRepository:
    """Repository for category database operations."""

    def __init__(self, session: AsyncSession):
        """Initialize repository with database session.

        Args:
            session: AsyncSession instance.
        """
        self.session = session

    async def get_by_external_id(
        self, source_app: SourceApp, external_id: str
    ) -> Optional[Category]:
        """Get category by source app and external ID.

        Args:
            source_app: Source application.
            external_id: External category ID.

        Returns:
            Category or None if not found.
        """
        result = await self.session.execute(
            select(Category).where(
                Category.source_app == source_app.value,
                Category.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, category_data: CategoryCreate) -> Category:
        """Create a new category.

        Args:
            category_data: Category creation data.

        Returns:
            Created category.
        """
        category = Category(
            source_app=category_data.source_app.value,
            external_id=category_data.external_id,
            name=category_data.name,
            name_ar=category_data.name_ar,
            image_url=category_data.image_url,
            sort_order=category_data.sort_order,
        )
        self.session.add(category)
        await self.session.flush()
        return category

    async def upsert(self, category_data: CategoryCreate) -> tuple[Category, bool]:
        """Create or update a category.

        Args:
            category_data: Category data.

        Returns:
            Tuple of (category, is_new).
        """
        existing = await self.get_by_external_id(
            category_data.source_app, category_data.external_id
        )

        if existing:
            existing.name = category_data.name
            existing.name_ar = category_data.name_ar
            existing.image_url = category_data.image_url
            existing.sort_order = category_data.sort_order
            await self.session.flush()
            return existing, False
        else:
            category = await self.create(category_data)
            return category, True
