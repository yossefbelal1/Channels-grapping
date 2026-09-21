-- ============================================================
-- Migration: v4 Exchange & Cross-Promotion Network Intelligence Engine
-- Date: 2026-09-21
-- Description:
--   1. Add exchange affinity, network value, and growth openness scores to leads
--   2. Add exchange hub and exchange seed flags
--   3. Add structured exchange evidence jsonb
--   4. Supporting indexes for rapid traversal and ranking
-- ============================================================

ALTER TABLE leads ADD COLUMN IF NOT EXISTS exchange_affinity_score INT DEFAULT 0;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS network_value_score INT DEFAULT 0;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS growth_openness_score INT DEFAULT 0;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS is_exchange_hub BOOLEAN DEFAULT FALSE;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS is_exchange_seed BOOLEAN DEFAULT FALSE;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS exchange_evidence JSONB DEFAULT '{}'::jsonb;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS cluster_id VARCHAR(64);

-- Indexes for performance and prioritization queries
CREATE INDEX IF NOT EXISTS idx_leads_exchange_affinity 
    ON leads(exchange_affinity_score DESC) 
    WHERE status != 'rejected';

CREATE INDEX IF NOT EXISTS idx_leads_exchange_seeds 
    ON leads(is_exchange_seed, exchange_affinity_score DESC) 
    WHERE is_exchange_seed = TRUE;

CREATE INDEX IF NOT EXISTS idx_leads_exchange_hubs 
    ON leads(is_exchange_hub) 
    WHERE is_exchange_hub = TRUE;

CREATE INDEX IF NOT EXISTS idx_leads_cluster 
    ON leads(cluster_id) 
    WHERE cluster_id IS NOT NULL;
