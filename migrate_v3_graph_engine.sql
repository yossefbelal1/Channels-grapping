-- ============================================================
-- Migration: v3 Graph Engine Expansion
-- Date: 2026-06-24
-- Description:
--   1. Add `depth` column to leads table (graph traversal depth)
--   2. Create `seed_channels` table (AutoTele / external seed intake)
--   3. Add supporting indexes
--
-- This script is SAFE to run on a live database.
-- All operations use ADD COLUMN IF NOT EXISTS and CREATE TABLE IF NOT EXISTS.
-- ============================================================

-- 1. Add depth tracking to leads table
ALTER TABLE leads ADD COLUMN IF NOT EXISTS depth INT DEFAULT 0;
COMMENT ON COLUMN leads.depth IS 'Graph traversal depth: 0 = seed/keyword, 1 = discovered from seed, 2 = discovered from depth-1, etc.';

-- 2. Index for depth filtering (graph expander queries by depth)
CREATE INDEX IF NOT EXISTS idx_leads_depth ON leads(depth);

-- 3. Combined index for graph expander worker queries
CREATE INDEX IF NOT EXISTS idx_leads_graph_expansion
    ON leads(is_group, status, last_scan)
    WHERE status NOT IN ('rejected');

-- 4. seed_channels table: External seed intake (AutoTele / any external system)
--    External systems INSERT here; seed_intake_worker.py processes them.
CREATE TABLE IF NOT EXISTS seed_channels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_username VARCHAR(255) UNIQUE NOT NULL,
    source VARCHAR(100) DEFAULT 'autotele',   -- which system provided this seed
    notes TEXT,                               -- optional context from source system
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP
);

COMMENT ON TABLE seed_channels IS 'External seed channels from AutoTele or other systems. Processed by seed_intake_worker.py.';
COMMENT ON COLUMN seed_channels.source IS 'Source identifier: autotele, manual, web_scraper, etc.';
COMMENT ON COLUMN seed_channels.processed IS 'Whether this seed has been queued for validation.';

-- Index for polling unprocessed seeds efficiently
CREATE INDEX IF NOT EXISTS idx_seed_channels_processed
    ON seed_channels(processed, created_at)
    WHERE processed = FALSE;

-- ============================================================
-- Verification Queries (run after migration to confirm)
-- ============================================================
-- SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'leads' AND column_name = 'depth';
-- SELECT COUNT(*) FROM seed_channels;
-- \d leads
-- ============================================================
