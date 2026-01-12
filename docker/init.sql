-- PostgreSQL initialization script for Competitor Price Scraping
-- This runs automatically when the database container is first created

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For fuzzy text search

-- Performance indexes (will be created by Alembic, but good to have as reference)
-- CREATE INDEX IF NOT EXISTS idx_products_source_app ON products(source_app);
-- CREATE INDEX IF NOT EXISTS idx_products_barcode ON products(barcode);
-- CREATE INDEX IF NOT EXISTS idx_products_name_trgm ON products USING gin(name gin_trgm_ops);
-- CREATE INDEX IF NOT EXISTS idx_price_records_product_id ON price_records(product_id);
-- CREATE INDEX IF NOT EXISTS idx_price_records_recorded_at ON price_records(recorded_at);

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE scraping_db TO scraper;
