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


class Brand(Base):
    """Product brands from competitor apps."""
    __tablename__ = "brands"

    id = Column(Integer, primary_key=True)
    source_app = Column(String(50), nullable=False)
    external_id = Column(String(255), nullable=False)
    name = Column(String(500), nullable=False)
    name_ar = Column(String(500))
    image_url = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    products = relationship("Product", back_populates="brand_rel")

    __table_args__ = (
        UniqueConstraint("source_app", "external_id", name="uq_brand_source_external"),
        Index("idx_brand_source", "source_app"),
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
    brand_id = Column(Integer, ForeignKey("brands.id"))
    brand = Column(String(255))  # Legacy: external brand ID as string
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
    brand_rel = relationship("Brand", back_populates="products")
    units = relationship("ProductUnit", back_populates="product", order_by="ProductUnit.factor")
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
        Index("idx_product_brand", "brand_id"),
    )

    @property
    def latest_price(self):
        """Get the most recent price record."""
        if self.price_records:
            return self.price_records[0]
        return None


class ProductUnit(Base):
    """Product units/packaging options with different prices."""
    __tablename__ = "product_units"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    external_id = Column(String(255))  # Unit code from API (e.g., U_Code for Ben Soliman)
    name = Column(String(255), nullable=False)  # Unit name (كرتونة, زجاجة, كيس, etc.)
    name_ar = Column(String(255))
    factor = Column(Integer, default=1)  # How many base units (e.g., 12 bottles per case)
    barcode = Column(String(100))  # Unit-specific barcode
    is_base_unit = Column(Boolean, default=False)  # True if this is the smallest unit
    min_quantity = Column(Integer, default=1)
    max_quantity = Column(Integer)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    product = relationship("Product", back_populates="units")
    price_records = relationship("PriceRecord", back_populates="unit")

    __table_args__ = (
        UniqueConstraint("product_id", "external_id", name="uq_product_unit_external"),
        Index("idx_product_unit_product", "product_id"),
        Index("idx_product_unit_barcode", "barcode"),
    )


class PriceRecord(Base):
    """Historical price records for products/units."""
    __tablename__ = "price_records"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    unit_id = Column(Integer, ForeignKey("product_units.id"))  # Link to specific unit
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
    unit = relationship("ProductUnit", back_populates="price_records")
    scrape_job = relationship("ScrapeJob", back_populates="price_records")

    __table_args__ = (
        Index("idx_price_product_time", "product_id", "recorded_at"),
        Index("idx_price_unit_time", "unit_id", "recorded_at"),
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


class APIKey(Base):
    """API keys for authentication."""
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True)
    key_hash = Column(String(64), unique=True, nullable=False)  # SHA256 hash
    name = Column(String(100), nullable=False)
    scopes = Column(ARRAY(String), default=["read"])  # ["read", "write", "admin"]
    rate_limit_per_minute = Column(Integer, default=60)
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime(timezone=True))
    last_used_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("idx_api_key_hash", "key_hash"),
        Index("idx_api_key_active", "is_active"),
    )


class ProductLink(Base):
    """Cross-app product links for matching same products across different apps."""
    __tablename__ = "product_links"

    id = Column(Integer, primary_key=True)
    product_a_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    product_b_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    # Unit-level linking (optional - null means link is at product level)
    unit_a_id = Column(Integer, ForeignKey("product_units.id"), nullable=True)
    unit_b_id = Column(Integer, ForeignKey("product_units.id"), nullable=True)
    link_type = Column(String(50), default="manual")  # barcode, manual, suggested, verified, unit_barcode
    confidence_score = Column(Numeric(5, 4))  # 0.0000 to 1.0000 for suggested links
    match_reason = Column(String(255))  # Description of why products were linked
    verified_by = Column(String(100))  # Who verified the link
    verified_at = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    product_a = relationship("Product", foreign_keys=[product_a_id], backref="links_as_a")
    product_b = relationship("Product", foreign_keys=[product_b_id], backref="links_as_b")
    unit_a = relationship("ProductUnit", foreign_keys=[unit_a_id], backref="links_as_a")
    unit_b = relationship("ProductUnit", foreign_keys=[unit_b_id], backref="links_as_b")

    __table_args__ = (
        # Ensure we don't create duplicate links (A-B same as B-A, including units)
        UniqueConstraint("product_a_id", "product_b_id", "unit_a_id", "unit_b_id", name="uq_product_unit_link"),
        Index("idx_product_link_a", "product_a_id"),
        Index("idx_product_link_b", "product_b_id"),
        Index("idx_product_link_unit_a", "unit_a_id"),
        Index("idx_product_link_unit_b", "unit_b_id"),
        Index("idx_product_link_type", "link_type"),
        Index("idx_product_link_active", "is_active"),
    )


class ScheduleConfig(Base):
    """Scraper schedule configuration per app."""
    __tablename__ = "schedule_configs"

    id = Column(Integer, primary_key=True)
    source_app = Column(String(50), unique=True, nullable=False)
    is_enabled = Column(Boolean, default=True)
    cron_expression = Column(String(100), default="0 * * * *")  # Default: every hour
    job_type = Column(String(50), default="full")  # full, incremental, categories
    max_concurrent_requests = Column(Integer, default=3)
    request_delay_ms = Column(Integer, default=1000)
    last_run_at = Column(DateTime(timezone=True))
    next_run_at = Column(DateTime(timezone=True))
    last_run_status = Column(String(50))  # completed, failed
    last_run_products = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("idx_schedule_app", "source_app"),
        Index("idx_schedule_enabled", "is_enabled"),
    )


class Banner(Base):
    """Promotional banners/sliders from competitor apps."""
    __tablename__ = "banners"

    id = Column(Integer, primary_key=True)
    source_app = Column(String(50), nullable=False)
    external_id = Column(String(255), nullable=False)
    title = Column(String(500))
    title_ar = Column(String(500))
    image_url = Column(Text, nullable=False)
    link_type = Column(String(50))  # product, category, offer, external, none
    link_target_id = Column(String(255))  # ID of linked entity
    link_url = Column(Text)  # Full URL if external link
    position = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    start_date = Column(DateTime(timezone=True))
    end_date = Column(DateTime(timezone=True))
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("source_app", "external_id", name="uq_banner_source_external"),
        Index("idx_banner_source", "source_app"),
        Index("idx_banner_active", "is_active"),
    )


class ExportJob(Base):
    """Export job tracking for async exports."""
    __tablename__ = "export_jobs"

    id = Column(Integer, primary_key=True)
    job_type = Column(String(50), nullable=False)  # products_csv, prices_csv, images_zip, comparison
    status = Column(String(50), default="pending")  # pending, processing, completed, failed
    parameters = Column(JSONB)  # Export parameters (filters, format, etc.)
    file_path = Column(Text)  # Path to generated file
    file_name = Column(String(255))  # Original filename
    file_size_bytes = Column(Integer)
    records_count = Column(Integer)
    progress_percent = Column(Integer, default=0)
    error_message = Column(Text)
    requested_by = Column(String(100))  # API key name or user
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))  # When file will be deleted
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_export_status", "status"),
        Index("idx_export_type", "job_type"),
    )
