-- Migration v10: Adaptive Discovery & Self-Learning Engine
-- Grounds knowledge extraction in Tamer's Admin Channels (Gold Positive Corpus) and rejected leads (Negative Corpus)

CREATE TABLE IF NOT EXISTS corpus_channels (
    id SERIAL PRIMARY KEY,
    channel_id VARCHAR(64),
    channel_username VARCHAR(128),
    title TEXT,
    corpus_type VARCHAR(32) NOT NULL, -- 'gold_admin', 'validated_tier_a', 'negative_spam'
    is_admin BOOLEAN DEFAULT FALSE,
    is_creator BOOLEAN DEFAULT FALSE,
    member_count INT DEFAULT 0,
    about TEXT,
    sample_posts JSONB DEFAULT '[]'::jsonb,
    sample_posts_count INT DEFAULT 0,
    last_harvested_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_corpus_channel_username UNIQUE (channel_username)
);

CREATE TABLE IF NOT EXISTS discovered_signals (
    id SERIAL PRIMARY KEY,
    signal_type VARCHAR(32) NOT NULL, -- 'keyword', 'phrase', 'symbol', 'domain', 'syntax_pattern', 'naming_pattern'
    signal_value TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    category VARCHAR(32) DEFAULT 'general_trading', -- 'forex', 'crypto', 'gold', 'signals', 'commercial', 'negative_spam'
    status VARCHAR(16) DEFAULT 'observed', -- 'observed', 'candidate', 'validated', 'active', 'deprecated'
    confidence_score FLOAT DEFAULT 0.5,
    contrast_score FLOAT DEFAULT 0.0,
    positive_support_count INT DEFAULT 1,
    negative_penalty_count INT DEFAULT 0,
    provenance_sources JSONB DEFAULT '[]'::jsonb,
    evidence_samples JSONB DEFAULT '[]'::jsonb,
    discovery_count INT DEFAULT 0,
    last_yielded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_signal_type_value UNIQUE (signal_type, signal_value)
);

CREATE INDEX IF NOT EXISTS idx_discovered_signals_status ON discovered_signals (status);
CREATE INDEX IF NOT EXISTS idx_discovered_signals_type ON discovered_signals (signal_type);
CREATE INDEX IF NOT EXISTS idx_discovered_signals_confidence ON discovered_signals (confidence_score DESC);
CREATE INDEX IF NOT EXISTS idx_corpus_channels_type ON corpus_channels (corpus_type);
