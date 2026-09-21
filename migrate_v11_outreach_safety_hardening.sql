-- ============================================================================
-- Migration: v11 Outreach Safety Hardening & Risk Minimization
-- ============================================================================

-- 1. Migrate all existing un-reviewed 'pending' campaign logs to 'pending_review'
-- This guarantees no queued messages are automatically dispatched without approval
UPDATE campaign_logs 
SET status = 'pending_review' 
WHERE status = 'pending';

-- 2. Alter column default to 'pending_review' for future insertions
DO $$
BEGIN
    ALTER TABLE campaign_logs ALTER COLUMN status SET DEFAULT 'pending_review';
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Could not set default on campaign_logs.status: %', SQLERRM;
END $$;

-- 3. Create optimized partial index for campaign review and approved dispatches
CREATE INDEX IF NOT EXISTS idx_campaign_logs_status_review 
ON campaign_logs(status) 
WHERE status IN ('pending_review', 'approved');

-- 4. Create index on leads next_eligible_at and last_contact_at for cooldown enforcement
CREATE INDEX IF NOT EXISTS idx_leads_contact_cooldown 
ON leads(last_contact_at, next_eligible_at);

-- Verification Notice
DO $$
DECLARE
    pending_review_count INT;
BEGIN
    SELECT COUNT(*) INTO pending_review_count FROM campaign_logs WHERE status = 'pending_review';
    RAISE NOTICE 'Migration v11 complete: % records set to pending_review.', pending_review_count;
END $$;
