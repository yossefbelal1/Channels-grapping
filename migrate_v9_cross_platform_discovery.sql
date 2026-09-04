-- ============================================================================
-- Migration: V9 Cross-Platform Unified Discovery Architecture
-- Extends leads, channel_edges, and discovery tracking to support:
-- Telegram, TikTok, Facebook, and Web entities and cross-platform relationships.
-- ============================================================================

-- 1. Extend leads table with cross-platform identity columns
ALTER TABLE leads
    ADD COLUMN IF NOT EXISTS platform VARCHAR(50) DEFAULT 'telegram',
    ADD COLUMN IF NOT EXISTS entity_type VARCHAR(50) DEFAULT 'channel',
    ADD COLUMN IF NOT EXISTS canonical_id VARCHAR(500),
    ADD COLUMN IF NOT EXISTS url TEXT,
    ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;

-- 2. Backfill existing Telegram leads with canonical identity
UPDATE leads
SET 
    platform = 'telegram',
    entity_type = CASE WHEN is_group = true THEN 'group' ELSE 'channel' END,
    canonical_id = 'telegram:' || channel_username,
    url = 'https://t.me/' || channel_username
WHERE canonical_id IS NULL;

-- 3. Create indexes for fast lookup and deduplication
CREATE INDEX IF NOT EXISTS idx_leads_platform_canonical ON leads(platform, canonical_id);
CREATE INDEX IF NOT EXISTS idx_leads_canonical_lower ON leads(platform, LOWER(canonical_id));
CREATE INDEX IF NOT EXISTS idx_leads_platform ON leads(platform);
CREATE INDEX IF NOT EXISTS idx_leads_entity_type ON leads(entity_type);

-- 4. Extend channel_edges for cross-platform multi-edge graph
ALTER TABLE channel_edges
    ADD COLUMN IF NOT EXISTS source_platform VARCHAR(50) DEFAULT 'telegram',
    ADD COLUMN IF NOT EXISTS target_platform VARCHAR(50) DEFAULT 'telegram';

-- Backfill channel_edges platform data from leads table
UPDATE channel_edges ce
SET 
    source_platform = COALESCE(l_src.platform, 'telegram'),
    target_platform = COALESCE(l_tgt.platform, 'telegram')
FROM leads l_src, leads l_tgt
WHERE ce.source_channel_id = l_src.id AND ce.target_channel_id = l_tgt.id
  AND (ce.source_platform IS NULL OR ce.target_platform IS NULL);

CREATE INDEX IF NOT EXISTS idx_channel_edges_source_platform ON channel_edges(source_platform);
CREATE INDEX IF NOT EXISTS idx_channel_edges_target_platform ON channel_edges(target_platform);

-- 5. Extend discovery_sources for multi-platform telemetry
ALTER TABLE discovery_sources
    ADD COLUMN IF NOT EXISTS source_platform VARCHAR(50) DEFAULT 'telegram';
