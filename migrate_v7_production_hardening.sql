-- ============================================================================
-- Migration: v7 Production Hardening Schema
-- ============================================================================

-- 1. Add Production Hardening columns to leads table
DO $$
BEGIN
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS last_scanned_message_id BIGINT DEFAULT 0;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS graph_importance_score INT DEFAULT 0;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS crawl_interval_minutes INT DEFAULT 1440;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS consecutive_crawl_failures INT DEFAULT 0;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS last_crawl_at TIMESTAMPTZ;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS last_successful_crawl_at TIMESTAMPTZ;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS scan_depth_tier VARCHAR(32) DEFAULT 'standard';
EXCEPTION
    WHEN duplicate_column THEN NULL;
END $$;

-- 2. Channel Memberships table: Track controlled join/leave lifecycle and TTL research slots
CREATE TABLE IF NOT EXISTS channel_memberships (
    id SERIAL PRIMARY KEY,
    channel_id VARCHAR(64) NOT NULL,
    channel_username VARCHAR(255),
    account_session VARCHAR(128) NOT NULL,
    joined_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    leave_at TIMESTAMPTZ,
    membership_reason VARCHAR(64) DEFAULT 'deep_scan',
    current_state VARCHAR(32) DEFAULT 'ACTIVE', -- ACTIVE, SCHEDULED_LEAVE, LEFT, FAILED
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 3. Crawl Jobs table: Track distributed crawl execution and watermark updates
CREATE TABLE IF NOT EXISTS crawl_jobs (
    job_id UUID PRIMARY KEY,
    channel_id VARCHAR(64) NOT NULL,
    channel_username VARCHAR(255),
    job_type VARCHAR(64) DEFAULT 'incremental', -- incremental, deep_scan, revalidation
    activity_class VARCHAR(32) DEFAULT 'NORMAL', -- HOT, WARM, NORMAL, COLD, DORMANT
    priority VARCHAR(32) DEFAULT 'normal',
    scheduled_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    executed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    status VARCHAR(32) DEFAULT 'pending', -- pending, running, completed, failed
    error_message TEXT,
    watermark_used BIGINT DEFAULT 0,
    new_watermark BIGINT DEFAULT 0,
    posts_scanned INT DEFAULT 0,
    target_queue VARCHAR(64) DEFAULT 'queue:normal',
    payload TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

DO $$
BEGIN
    ALTER TABLE crawl_jobs ADD COLUMN IF NOT EXISTS target_queue VARCHAR(64) DEFAULT 'queue:normal';
    ALTER TABLE crawl_jobs ADD COLUMN IF NOT EXISTS payload TEXT;
EXCEPTION
    WHEN duplicate_column THEN NULL;
END $$;

-- 4. Indexes for Optimized Scheduling, Graph and Watermark Queries
CREATE INDEX IF NOT EXISTS idx_leads_next_crawl ON leads(next_crawl_at, activity_class, lead_score DESC) WHERE next_crawl_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_leads_last_scanned_msg ON leads(last_scanned_message_id);
CREATE INDEX IF NOT EXISTS idx_leads_graph_importance ON leads(graph_importance_score DESC);
CREATE INDEX IF NOT EXISTS idx_channel_memberships_state ON channel_memberships(current_state, leave_at);
CREATE INDEX IF NOT EXISTS idx_channel_memberships_channel ON channel_memberships(channel_id, account_session);
CREATE INDEX IF NOT EXISTS idx_crawl_jobs_status_sched ON crawl_jobs(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_crawl_jobs_channel ON crawl_jobs(channel_id, completed_at DESC);
