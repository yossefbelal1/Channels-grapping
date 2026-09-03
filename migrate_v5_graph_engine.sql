-- ============================================================================
-- Migration: v5 Production-Grade Graph Intelligence & Discovery Schema
-- ============================================================================

-- 1. Multi-Edge Graph Table: Rich relationship modeling with provenance & confidence
CREATE TABLE IF NOT EXISTS channel_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_channel_id UUID REFERENCES leads(id) ON DELETE CASCADE,
    target_channel_id UUID REFERENCES leads(id) ON DELETE CASCADE,
    relation_type VARCHAR(50) NOT NULL, -- 'mention', 'forwarded_from', 'promoted', 'linked', 'recommended'
    confidence INT DEFAULT 100,         -- Confidence score (0 to 100)
    evidence TEXT,                      -- Snippet of post/mention demonstrating relationship
    occurrence_count INT DEFAULT 1,     -- Frequency of observed relationship
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb,
    CONSTRAINT uq_channel_edge UNIQUE (source_channel_id, target_channel_id, relation_type)
);

CREATE INDEX IF NOT EXISTS idx_channel_edges_source ON channel_edges(source_channel_id);
CREATE INDEX IF NOT EXISTS idx_channel_edges_target ON channel_edges(target_channel_id);
CREATE INDEX IF NOT EXISTS idx_channel_edges_rel ON channel_edges(relation_type);
CREATE INDEX IF NOT EXISTS idx_channel_edges_last_seen ON channel_edges(last_seen);

-- 2. Multi-Source Provenance & Discovery Tracking
CREATE TABLE IF NOT EXISTS channel_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id UUID REFERENCES leads(id) ON DELETE CASCADE,
    source_type VARCHAR(50) NOT NULL,   -- 'global_search', 'search_posts', 'recommendation', 'graph', 'forwards', 'web', 'seed'
    keyword_or_query VARCHAR(255),
    referrer_channel_id UUID REFERENCES leads(id) ON DELETE SET NULL,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb,
    CONSTRAINT uq_channel_source UNIQUE (channel_id, source_type, keyword_or_query, referrer_channel_id)
);

CREATE INDEX IF NOT EXISTS idx_channel_sources_channel ON channel_sources(channel_id);
CREATE INDEX IF NOT EXISTS idx_channel_sources_type ON channel_sources(source_type);

-- 3. Historical Metric Snapshots (Growth & Activity Tracking)
CREATE TABLE IF NOT EXISTS channel_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id UUID REFERENCES leads(id) ON DELETE CASCADE,
    member_count INT,
    post_count INT,
    posts_24h INT DEFAULT 0,
    posts_7d INT DEFAULT 0,
    posts_30d INT DEFAULT 0,
    avg_views_per_post INT,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_channel_snapshots_channel_time ON channel_snapshots(channel_id, recorded_at DESC);

-- 4. Structured Contacts Table
CREATE TABLE IF NOT EXISTS channel_contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id UUID REFERENCES leads(id) ON DELETE CASCADE,
    contact_type VARCHAR(50) NOT NULL, -- 'owner', 'admin', 'support', 'whatsapp', 'website', 'email', 'linktree', 'social'
    value VARCHAR(255) NOT NULL,
    confidence INT DEFAULT 100,
    source VARCHAR(50) DEFAULT 'bio',  -- 'bio', 'pinned_post', 'recent_post', 'manual'
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_channel_contact UNIQUE (channel_id, contact_type, value)
);

CREATE INDEX IF NOT EXISTS idx_channel_contacts_channel ON channel_contacts(channel_id);
CREATE INDEX IF NOT EXISTS idx_channel_contacts_type_val ON channel_contacts(contact_type, value);

-- 5. Search Checkpoints (Resumable Global Search State)
CREATE TABLE IF NOT EXISTS discovery_checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    search_type VARCHAR(50) NOT NULL,  -- 'messages_search_global', 'channels_search_posts', 'web_search'
    query_key VARCHAR(255) NOT NULL,
    last_offset_rate INT DEFAULT 0,
    last_offset_id INT DEFAULT 0,
    last_offset_date TIMESTAMP,
    page_number INT DEFAULT 1,
    total_yield INT DEFAULT 0,
    status VARCHAR(50) DEFAULT 'in_progress', -- 'in_progress', 'completed', 'rate_limited'
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_discovery_checkpoint UNIQUE (search_type, query_key)
);

CREATE INDEX IF NOT EXISTS idx_discovery_checkpoints_type_status ON discovery_checkpoints(search_type, status);

-- 6. Dynamic Crawl Scheduler Jobs
CREATE TABLE IF NOT EXISTS crawl_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id UUID REFERENCES leads(id) ON DELETE CASCADE,
    job_type VARCHAR(50) NOT NULL,     -- 'cheap_validation', 'deep_scan', 'graph_expansion', 'recommendations'
    priority VARCHAR(20) DEFAULT 'normal', -- 'critical', 'high', 'normal', 'low'
    activity_class VARCHAR(20) DEFAULT 'WARM', -- 'HOT', 'WARM', 'COLD', 'DORMANT'
    status VARCHAR(20) DEFAULT 'queued',       -- 'queued', 'running', 'completed', 'failed'
    scheduled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    executed_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    retry_count INT DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_crawl_jobs_status_sched ON crawl_jobs(status, scheduled_at) WHERE status = 'queued';
CREATE INDEX IF NOT EXISTS idx_crawl_jobs_channel ON crawl_jobs(channel_id);

-- 7. Add Multi-Dimensional Scoring Columns to leads table
DO $$
BEGIN
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS forex_score INT DEFAULT 0;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS trading_score INT DEFAULT 0;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS signal_score INT DEFAULT 0;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS gold_score INT DEFAULT 0;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS activity_score INT DEFAULT 0;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS growth_score INT DEFAULT 0;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS commercial_score INT DEFAULT 0;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS contact_score INT DEFAULT 0;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS legitimacy_score INT DEFAULT 100;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS discovery_score INT DEFAULT 0;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS new_channel_score INT DEFAULT 0;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS activity_class VARCHAR(20) DEFAULT 'WARM';
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS posts_24h INT DEFAULT 0;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS posts_7d INT DEFAULT 0;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS posts_30d INT DEFAULT 0;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS avg_posts_per_day NUMERIC(6,2) DEFAULT 0;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS discovery_count INT DEFAULT 1;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS discovered_by TEXT[] DEFAULT ARRAY['unknown'::TEXT];
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS owner_username VARCHAR(255);
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS admin_username VARCHAR(255);
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS creation_date TIMESTAMP;
    ALTER TABLE leads ADD COLUMN IF NOT EXISTS next_crawl_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
EXCEPTION
    WHEN duplicate_column THEN NULL;
END $$;

-- Additional Indexes for Leads
CREATE INDEX IF NOT EXISTS idx_leads_activity_class ON leads(activity_class);
CREATE INDEX IF NOT EXISTS idx_leads_next_crawl ON leads(next_crawl_at);
CREATE INDEX IF NOT EXISTS idx_leads_forex_score ON leads(forex_score);
CREATE INDEX IF NOT EXISTS idx_leads_new_channel ON leads(new_channel_score);
CREATE INDEX IF NOT EXISTS idx_leads_discovery_count ON leads(discovery_count);
