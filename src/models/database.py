"""SQLAlchemy ORM models for the database."""
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Numeric,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class Category(Base):
    """Product categories from competitor apps."""
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    source_app = Column(String(50), nullable=False)
    external_id = Column(String(255), nullable=False)
    name = Column(String(500), nullable=False)
    name_ar = Column(String(500))
    parent_id = Column(Integer, ForeignKey("categories.id"))
    image_url = Column(Text)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    parent = relationship("Category", remote_side=[id], backref="children")
    products = relationship("Product", back_populates="category")

    __table_args__ = (
        UniqueConstraint("source_app", "external_id", name="uq_category_source_external"),
        Index("idx_category_source", "source_app"),
    )


class Product(Base):
    """Products scraped from competitor apps."""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    source_app = Column(String(50), nullable=False)
    external_id = Column(String(255), nullable=False)
    name = Column(String(1000), nullable=False)
    name_ar = Column(String(1000))
    description = Column(Text)
    description_ar = Column(Text)
    category_id = Column(Integer, ForeignKey("categories.id"))
    brand = Column(String(255))
    sku = Column(String(255))
    barcode = Column(String(100))  # For cross-app product matching
    image_url = Column(Text)
    additional_images = Column(ARRAY(Text))
    unit_type = Column(String(50), default="piece")
    unit_value = Column(Numeric(10, 3))
    min_order_quantity = Column(Integer, default=1)
    extra_data = Column(JSONB)  # Flexible storage for app-specific data
    is_active = Column(Boolean, default=True)
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    category = relationship("Category", back_populates="products")
    price_records = relationship(
        "PriceRecord",
        back_populates="product",
        order_by="desc(PriceRecord.recorded_at)"
    )
    offers = relationship("Offer", back_populates="product")

    __table_args__ = (
        UniqueConstraint("source_app", "external_id", name="uq_product_source_external"),
        Index("idx_product_source", "source_app"),
        Index("idx_product_barcode", "barcode"),
        Index("idx_product_sku", "sku"),
    )

    @property
    def latest_price(self):
        """Get the most recent price record."""
        if self.price_records:
            return self.price_records[0]
        return None


class PriceRecord(Base):
    """Historical price records for products."""
    __tablename__ = "price_records"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    source_app = Column(String(50), nullable=False)
    price = Column(Numeric(12, 2), nullable=False)
    original_price = Column(Numeric(12, 2))  # Price before discount
    discount_percentage = Column(Numeric(5, 2))
    currency = Column(String(10), default="EGP")
    is_available = Column(Boolean, default=True)
    stock_status = Column(String(100))  # in_stock, out_of_stock, limited
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())
    scrape_job_id = Column(Integer, ForeignKey("scrape_jobs.id"))

    # Relationships
    product = relationship("Product", back_populates="price_records")
    scrape_job = relationship("ScrapeJob", back_populates="price_records")

    __table_args__ = (
        Index("idx_price_product_time", "product_id", "recorded_at"),
        Index("idx_price_recorded_at", "recorded_at"),
    )


class Offer(Base):
    """Promotional offers and discounts."""
    __tablename__ = "offers"

    id = Column(Integer, primary_key=True)
    source_app = Column(String(50), nullable=False)
    external_id = Column(String(255), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"))
    title = Column(String(500), nullable=False)
    title_ar = Column(String(500))
    description = Column(Text)
    description_ar = Column(Text)
    discount_type = Column(String(50))  # percentage, fixed, buy_x_get_y
    discount_value = Column(Numeric(12, 2))
    min_quantity = Column(Integer)
    max_quantity = Column(Integer)
    start_date = Column(DateTime(timezone=True))
    end_date = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)
    extra_data = Column(JSONB)
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    product = relationship("Product", back_populates="offers")

    __table_args__ = (
        UniqueConstraint("source_app", "external_id", name="uq_offer_source_external"),
        Index("idx_offer_active", "is_active", "end_date"),
    )


class ScrapeJob(Base):
    """Tracking for scraping jobs."""
    __tablename__ = "scrape_jobs"

    id = Column(Integer, primary_key=True)
    source_app = Column(String(50), nullable=False)
    job_type = Column(String(50), nullable=False)  # full, incremental, categories, offers
    status = Column(String(50), default="pending")  # pending, running, completed, failed
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    products_scraped = Column(Integer, default=0)
    products_updated = Column(Integer, default=0)
    products_new = Column(Integer, default=0)
    errors_count = Column(Integer, default=0)
    error_details = Column(JSONB)
    extra_data = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    price_records = relationship("PriceRecord", back_populates="scrape_job")

    __table_args__ = (
        Index("idx_scrape_job_source_status", "source_app", "status"),
    )


class Credential(Base):
    """Encrypted credentials for app authentication."""
    __tablename__ = "credentials"

    id = Column(Integer, primary_key=True)
    source_app = Column(String(50), nullable=False, unique=True)
    username = Column(String(255), nullable=False)
    password_encrypted = Column(Text, nullable=False)  # Encrypted with Fernet
    access_token = Column(Text)
    refresh_token = Column(Text)
    token_expires_at = Column(DateTime(timezone=True))
    device_id = Column(String(255))
    additional_headers = Column(JSONB)  # Store any app-specific headers
    is_active = Column(Boolean, default=True)
    last_login_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
