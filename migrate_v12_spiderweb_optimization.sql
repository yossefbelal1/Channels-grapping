-- ============================================================================
-- Migration: v12 Spiderweb Performance Optimization & Exchange Prioritization
-- ============================================================================

-- 1. Case-insensitive index on channel_username to accelerate lookups across crawlers & validators
CREATE INDEX IF NOT EXISTS idx_leads_channel_username_lower 
ON leads (LOWER(channel_username));

-- 2. Case-insensitive partial index on contact_username to speed up deduplication & auto-enrollment checks
CREATE INDEX IF NOT EXISTS idx_leads_contact_username_lower 
ON leads (LOWER(contact_username)) 
WHERE contact_username IS NOT NULL;

-- 3. Composite partial index for prioritizing ad exchange seeds and hubs during graph traversal
CREATE INDEX IF NOT EXISTS idx_leads_exchange_priority 
ON leads (exchange_affinity_score DESC, member_count ASC) 
WHERE status != 'rejected';

-- 4. Composite partial index on last_graph_scan for high-value priority queues
CREATE INDEX IF NOT EXISTS idx_leads_graph_scan_prio 
ON leads (last_graph_scan ASC NULLS FIRST, lead_score DESC) 
WHERE status != 'rejected';

-- Verification Notice
DO $$
BEGIN
    RAISE NOTICE 'Migration v12 complete: Spiderweb optimization indexes applied successfully.';
END $$;
