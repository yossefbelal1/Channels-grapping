-- Create Facebook Bot tables

CREATE TABLE IF NOT EXISTS fb_accounts (
    id UUID PRIMARY KEY,
    session_name VARCHAR(100) UNIQUE NOT NULL,
    fb_username VARCHAR(255),
    fb_password VARCHAR(255),
    cookies JSONB,                      -- Stored cookies in JSON format
    proxy VARCHAR(500),                 -- proxy string "http://user:pass@ip:port"
    status VARCHAR(50) DEFAULT 'active', -- active, inactive, frozen, banned
    comments_sent_today INT DEFAULT 0,
    last_use TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fb_target_groups (
    id UUID PRIMARY KEY,
    group_url VARCHAR(500) UNIQUE NOT NULL,
    group_name VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fb_posts_queue (
    id UUID PRIMARY KEY,
    post_url VARCHAR(500) UNIQUE NOT NULL,
    group_url VARCHAR(500) REFERENCES fb_target_groups(group_url) ON DELETE CASCADE,
    post_text TEXT,
    status VARCHAR(50) DEFAULT 'pending', -- pending, commented, failed, skipped
    error_message TEXT,
    discovered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fb_campaign_logs (
    id UUID PRIMARY KEY,
    account_id UUID REFERENCES fb_accounts(id) ON DELETE SET NULL,
    post_id UUID REFERENCES fb_posts_queue(id) ON DELETE CASCADE,
    comment_text TEXT NOT NULL,
    status VARCHAR(50) DEFAULT 'sent', -- sent, failed
    error_message TEXT,
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fb_comment_templates (
    id UUID PRIMARY KEY,
    message_template TEXT NOT NULL,      -- Spintax format supported
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
