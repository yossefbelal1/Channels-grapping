-- LeadHunter CRM DB Schema Definition (v3 Autonomous Ecosystem)

CREATE TYPE tier_level AS ENUM ('Tier_A', 'Tier_B', 'Tier_C', 'Tier_D');

CREATE TYPE lead_status AS ENUM ('new', 'contacted', 'closed', 'rejected');

CREATE TABLE leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_username VARCHAR(255) UNIQUE NOT NULL,
    member_count INT,
    description TEXT,
    language VARCHAR(50),
    arabic_ratio INT, -- Rules-based Arabic language percentage (0 to 100)
    website VARCHAR(255),
    email VARCHAR(255),
    whatsapp VARCHAR(50),
    contact_username VARCHAR(255),
    
    -- Entity category (groups vs broadcast channels)
    is_group BOOLEAN DEFAULT FALSE,
    marketplace_score INT DEFAULT 0, -- Dynamic marketplace group rating (0 to 100)
    
    -- Business offerings
    vip BOOLEAN DEFAULT FALSE,
    premium BOOLEAN DEFAULT FALSE,
    subscription BOOLEAN DEFAULT FALSE,
    monthly_plans BOOLEAN DEFAULT FALSE,
    yearly_plans BOOLEAN DEFAULT FALSE,
    account_management BOOLEAN DEFAULT FALSE,
    copy_trading BOOLEAN DEFAULT FALSE,
    funded_accounts BOOLEAN DEFAULT FALSE,
    usdt_payments BOOLEAN DEFAULT FALSE,
    binance_payments BOOLEAN DEFAULT FALSE,
    
    -- Ratings and analysis
    lead_score INT,
    tier tier_level,
    ai_confidence INT DEFAULT 100, -- AI-free confidence rating
    status lead_status DEFAULT 'new',
    
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_scan TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP,
    last_graph_scan TIMESTAMP,

    -- Graph traversal depth (0 = seed/keyword, 1 = discovered from seed, etc.)
    depth INT DEFAULT 0,

    -- Multi-Dimensional Scoring & Intelligence (v5 & v6)
    forex_score INT DEFAULT 0,
    trading_score INT DEFAULT 0,
    signal_score INT DEFAULT 0,
    gold_score INT DEFAULT 0,
    activity_score INT DEFAULT 0,
    growth_score INT DEFAULT 0,
    commercial_score INT DEFAULT 0,
    contact_score INT DEFAULT 0,
    legitimacy_score INT DEFAULT 100,
    discovery_score INT DEFAULT 0,
    freshness_score INT DEFAULT 0,
    confidence_score INT DEFAULT 0,
    new_channel_score INT DEFAULT 0,
    classification VARCHAR(50) DEFAULT 'POSSIBLE_FOREX',
    scoring_evidence JSONB DEFAULT '{}'::jsonb,
    activity_class VARCHAR(20) DEFAULT 'WARM',
    posts_24h INT DEFAULT 0,
    posts_7d INT DEFAULT 0,
    posts_30d INT DEFAULT 0,
    avg_posts_per_day NUMERIC(6,2) DEFAULT 0,
    discovery_count INT DEFAULT 1,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    creation_date TIMESTAMP,
    next_crawl_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE blacklist (
    entity_username_or_link VARCHAR(255) PRIMARY KEY,
    reason TEXT,
    blacklisted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Partitioned table for millions of message logs
CREATE TABLE channel_posts (
    channel_username VARCHAR(255) REFERENCES leads(channel_username) ON DELETE CASCADE,
    message_id INT NOT NULL,
    message_text TEXT,
    timestamp TIMESTAMP NOT NULL,
    PRIMARY KEY (channel_username, message_id, timestamp)
) PARTITION BY RANGE (timestamp);

-- Monthly partitions
CREATE TABLE channel_posts_default PARTITION OF channel_posts DEFAULT;
CREATE TABLE channel_posts_2026_06 PARTITION OF channel_posts FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
CREATE TABLE channel_posts_2026_07 PARTITION OF channel_posts FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
CREATE TABLE channel_posts_2026_08 PARTITION OF channel_posts FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
CREATE TABLE channel_posts_2026_09 PARTITION OF channel_posts FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');

-- Ecosystem Graph representation
CREATE TABLE channel_graph (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_channel_id UUID REFERENCES leads(id) ON DELETE CASCADE,
    target_channel_id UUID REFERENCES leads(id) ON DELETE CASCADE,
    relation_type VARCHAR(100) NOT NULL, -- e.g. 'advertisement', 'mention', 'link'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_channel_id, target_channel_id)
);

-- Advanced Graph Edges with Occurrence Tracking and Confidence
CREATE TABLE channel_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_channel_id UUID REFERENCES leads(id) ON DELETE CASCADE,
    target_channel_id UUID REFERENCES leads(id) ON DELETE CASCADE,
    relation_type VARCHAR(100) NOT NULL,
    confidence INT DEFAULT 100,
    evidence TEXT,
    occurrence_count INT DEFAULT 1,
    metadata JSONB,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_channel_id, target_channel_id, relation_type)
);

-- Historical Metric Snapshots (Growth & Activity Tracking with Score Metrics)
CREATE TABLE IF NOT EXISTS channel_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id UUID REFERENCES leads(id) ON DELETE CASCADE,
    member_count INT,
    post_count INT,
    posts_24h INT DEFAULT 0,
    posts_7d INT DEFAULT 0,
    posts_30d INT DEFAULT 0,
    avg_views_per_post INT,
    lead_score INT DEFAULT 0,
    forex_score INT DEFAULT 0,
    activity_score INT DEFAULT 0,
    scores JSONB DEFAULT '{}'::jsonb,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Keyword Frequency Engine table
CREATE TABLE channel_keywords (
    channel_id UUID REFERENCES leads(id) ON DELETE CASCADE,
    keyword VARCHAR(100) NOT NULL,
    frequency INT DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (channel_id, keyword)
);

-- Marketplace Group Metrics table
CREATE TABLE IF NOT EXISTS group_metrics (
    group_id UUID PRIMARY KEY REFERENCES leads(id) ON DELETE CASCADE,
    messages_scanned INT DEFAULT 0,
    mentions_count INT DEFAULT 0,
    telegram_links_count INT DEFAULT 0,
    advertisements_count INT DEFAULT 0,
    marketplace_score INT DEFAULT 0,
    last_scan TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed Channels table: External seed intake from AutoTele and other systems
-- seed_intake_worker.py polls this table and pushes seeds to validation queues.
CREATE TABLE IF NOT EXISTS seed_channels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_username VARCHAR(255) UNIQUE NOT NULL,
    source VARCHAR(100) DEFAULT 'autotele',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP
);

-- Database indexes for optimized CRM and Graph queries
CREATE INDEX idx_leads_lead_score ON leads(lead_score);
CREATE INDEX idx_leads_status ON leads(status);
CREATE INDEX idx_leads_is_group ON leads(is_group);
CREATE INDEX idx_leads_depth ON leads(depth);
CREATE INDEX idx_channel_posts_username ON channel_posts(channel_username);
CREATE INDEX idx_channel_posts_timestamp ON channel_posts(timestamp);
CREATE INDEX idx_channel_graph_source ON channel_graph(source_channel_id);
CREATE INDEX idx_channel_graph_target ON channel_graph(target_channel_id);
CREATE INDEX idx_channel_graph_rel ON channel_graph(relation_type);
CREATE INDEX idx_channel_keywords_kw ON channel_keywords(keyword);
CREATE INDEX idx_group_metrics_last_scan ON group_metrics(last_scan);
CREATE INDEX idx_seed_channels_processed ON seed_channels(processed, created_at) WHERE processed = FALSE;

-- v4 Outreach Campaigns Engine
CREATE TABLE IF NOT EXISTS campaigns (
    id UUID PRIMARY KEY,
    message_text TEXT NOT NULL,
    media_path VARCHAR(255),
    status VARCHAR(20) DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS campaign_logs (
    id UUID PRIMARY KEY,
    campaign_id UUID REFERENCES campaigns(id) ON DELETE CASCADE,
    lead_id UUID REFERENCES leads(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'pending',
    error_message TEXT,
    sent_at TIMESTAMP
);

CREATE INDEX idx_campaign_logs_status ON campaign_logs(status);
CREATE INDEX idx_campaign_logs_campaign_id ON campaign_logs(campaign_id);
