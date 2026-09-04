-- ============================================================================
-- Migration: v10 Campaign Logs Invariant & Candidate State Hardening
-- ============================================================================

-- 1. Deduplicate any existing campaign_logs for the same (campaign_id, lead_id)
-- Keeps the most progressed row (sent > processing > retry_wait > pending > skipped > failed)
DELETE FROM campaign_logs a
USING campaign_logs b
WHERE a.id > b.id
  AND a.campaign_id = b.campaign_id
  AND a.lead_id = b.lead_id;

-- 2. Add Unique Index/Constraint on (campaign_id, lead_id) to prevent duplicate campaign recipients
CREATE UNIQUE INDEX IF NOT EXISTS uq_campaign_logs_campaign_lead 
ON campaign_logs(campaign_id, lead_id);

-- 3. Ensure leads table has candidate_status and verification columns for cross-platform
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'leads' AND column_name = 'candidate_status') THEN
        ALTER TABLE leads ADD COLUMN candidate_status VARCHAR(32) DEFAULT 'verified';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'leads' AND column_name = 'relevance_score') THEN
        ALTER TABLE leads ADD COLUMN relevance_score INT DEFAULT 0;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'leads' AND column_name = 'verified_at') THEN
        ALTER TABLE leads ADD COLUMN verified_at TIMESTAMP;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_leads_candidate_status ON leads(candidate_status);
CREATE INDEX IF NOT EXISTS idx_leads_relevance_score ON leads(relevance_score);
