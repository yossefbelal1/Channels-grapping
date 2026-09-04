-- =============================================================================
-- migrate_v8_outreach_intelligence.sql — Outreach Intelligence & Priority Ordering
-- 
-- Adds Commercial Fit, Service Need Inference, Freshness, and Priority Tiers (P0..P4)
-- All statements are safe and idempotent.
-- =============================================================================

-- ─── 1. Columns on leads table ───────────────────────────────────────────────

ALTER TABLE leads ADD COLUMN IF NOT EXISTS outreach_priority VARCHAR(10) DEFAULT 'P3';
ALTER TABLE leads ADD COLUMN IF NOT EXISTS outreach_priority_score INT DEFAULT 25;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS outreach_priority_reason TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS outreach_priority_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS commercial_fit_score INT DEFAULT 0;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS business_model_score INT DEFAULT 0;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS operational_complexity_score INT DEFAULT 0;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS commercial_intent_type VARCHAR(50) DEFAULT 'none';
ALTER TABLE leads ADD COLUMN IF NOT EXISTS commercial_intent_score INT DEFAULT 0;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS commercial_intent_evidence JSONB DEFAULT '{}'::jsonb;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS commercial_evidence JSONB DEFAULT '{}'::jsonb;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS likely_services TEXT[] DEFAULT '{}';
ALTER TABLE leads ADD COLUMN IF NOT EXISTS intent_detected_at TIMESTAMP;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS commercial_last_seen TIMESTAMP;

COMMENT ON COLUMN leads.outreach_priority IS 'Outreach priority tier: P0 (Immediate), P1 (Very High), P2 (High), P3 (Normal), P4 (Low)';
COMMENT ON COLUMN leads.outreach_priority_score IS 'Outreach priority score 0-100 combining commercial fit, business model, operations, forex relevance';
COMMENT ON COLUMN leads.outreach_priority_reason IS 'Human-readable explanation of why this channel has this priority';
COMMENT ON COLUMN leads.commercial_fit_score IS 'Component score for commercial fit (0-35)';
COMMENT ON COLUMN leads.business_model_score IS 'Component score for business model strength (0-20)';
COMMENT ON COLUMN leads.operational_complexity_score IS 'Component score for operational complexity (0-15)';
COMMENT ON COLUMN leads.likely_services IS 'Inferred service needs: channel_management, advertising_management, growth_marketing, verification, etc.';
COMMENT ON COLUMN leads.commercial_evidence IS 'Explainable structured evidence including models, promos, payment methods, CTAs';

-- ─── 2. Columns on campaign_logs table ───────────────────────────────────────

ALTER TABLE campaign_logs ADD COLUMN IF NOT EXISTS priority VARCHAR(10) DEFAULT 'P3';
ALTER TABLE campaign_logs ADD COLUMN IF NOT EXISTS priority_score INT DEFAULT 25;
ALTER TABLE campaign_logs ADD COLUMN IF NOT EXISTS priority_reason TEXT;
ALTER TABLE campaign_logs ADD COLUMN IF NOT EXISTS intent_type VARCHAR(50) DEFAULT 'none';
ALTER TABLE campaign_logs ADD COLUMN IF NOT EXISTS intent_evidence JSONB DEFAULT '{}'::jsonb;
ALTER TABLE campaign_logs ADD COLUMN IF NOT EXISTS commercial_fit_score INT DEFAULT 0;
ALTER TABLE campaign_logs ADD COLUMN IF NOT EXISTS likely_services TEXT[] DEFAULT '{}';

COMMENT ON COLUMN campaign_logs.priority IS 'Priority tier assigned for this campaign recipient (P0..P4)';
COMMENT ON COLUMN campaign_logs.priority_score IS 'Priority score 0-100 used for ordering pending dispatches';
COMMENT ON COLUMN campaign_logs.priority_reason IS 'Explainable reason for priority ranking';
COMMENT ON COLUMN campaign_logs.intent_type IS 'Detected commercial intent or primary business model';
COMMENT ON COLUMN campaign_logs.intent_evidence IS 'Structured evidence of commercial activity and service fit';

-- ─── 3. Indexes for high-speed priority dispatch & filtering ────────────────

CREATE INDEX IF NOT EXISTS idx_leads_outreach_priority
    ON leads(outreach_priority, outreach_priority_score DESC);

CREATE INDEX IF NOT EXISTS idx_leads_commercial_last_seen
    ON leads(commercial_last_seen DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_campaign_logs_priority_dispatch
    ON campaign_logs(campaign_id, status, priority, priority_score DESC);
