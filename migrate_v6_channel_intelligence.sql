-- ============================================================================
-- Migration: v6 Channel Intelligence & Smart Ranking Schema
-- ============================================================================

-- 1. Add Phase 3 Channel Intelligence columns to leads table
DO $$
BEGIN
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS freshness_score INT DEFAULT 0;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS confidence_score INT DEFAULT 0;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS classification VARCHAR(50) DEFAULT 'POSSIBLE_FOREX';
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS scoring_evidence JSONB DEFAULT '{}'::jsonb;
EXCEPTION
    WHEN duplicate_column THEN NULL;
END $$;

-- 2. Add Score Metrics to channel_snapshots table for historical tracking
DO $$
BEGIN
    ALTER TABLE channel_snapshots ADD COLUMN IF NOT EXISTS lead_score INT DEFAULT 0;
    ALTER TABLE channel_snapshots ADD COLUMN IF NOT EXISTS forex_score INT DEFAULT 0;
    ALTER TABLE channel_snapshots ADD COLUMN IF NOT EXISTS activity_score INT DEFAULT 0;
    ALTER TABLE channel_snapshots ADD COLUMN IF NOT EXISTS scores JSONB DEFAULT '{}'::jsonb;
EXCEPTION
    WHEN duplicate_column THEN NULL;
END $$;

-- 3. Indexes for Optimized Ranking and Classification Queries
CREATE INDEX IF NOT EXISTS idx_leads_classification ON leads(classification);
CREATE INDEX IF NOT EXISTS idx_leads_freshness ON leads(freshness_score);
CREATE INDEX IF NOT EXISTS idx_leads_confidence ON leads(confidence_score);
CREATE INDEX IF NOT EXISTS idx_channel_snapshots_lead_score ON channel_snapshots(channel_id, lead_score);
