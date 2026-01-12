-- Migration: Add unit_a_id and unit_b_id to product_links table
-- This enables unit-level linking between products across apps

-- Add unit_a_id column
ALTER TABLE product_links
ADD COLUMN IF NOT EXISTS unit_a_id INTEGER REFERENCES product_units(id);

-- Add unit_b_id column
ALTER TABLE product_links
ADD COLUMN IF NOT EXISTS unit_b_id INTEGER REFERENCES product_units(id);

-- Create indexes for unit columns
CREATE INDEX IF NOT EXISTS idx_product_link_unit_a ON product_links(unit_a_id);
CREATE INDEX IF NOT EXISTS idx_product_link_unit_b ON product_links(unit_b_id);

-- Drop old unique constraint and add new one that includes units
-- Note: The old constraint name is "uq_product_link"
ALTER TABLE product_links DROP CONSTRAINT IF EXISTS uq_product_link;
ALTER TABLE product_links ADD CONSTRAINT uq_product_unit_link
    UNIQUE (product_a_id, product_b_id, unit_a_id, unit_b_id);
