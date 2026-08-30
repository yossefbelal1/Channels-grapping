-- =============================================================================
-- migrate_outreach_engine.sql — Risk-Aware Outreach Engine Schema Extensions
-- 
-- All operations are idempotent (IF NOT EXISTS / ADD COLUMN IF NOT EXISTS).
-- Safe to re-run on existing databases without data loss.
-- =============================================================================

-- ─── New columns on campaign_logs ────────────────────────────────────────────

ALTER TABLE campaign_logs ADD COLUMN IF NOT EXISTS delivery_id UUID DEFAULT gen_random_uuid();
ALTER TABLE campaign_logs ADD COLUMN IF NOT EXISTS attempt_count INT DEFAULT 0;
ALTER TABLE campaign_logs ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMP;
ALTER TABLE campaign_logs ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMP;
ALTER TABLE campaign_logs ADD COLUMN IF NOT EXISTS last_error TEXT;
ALTER TABLE campaign_logs ADD COLUMN IF NOT EXISTS risk_level VARCHAR(20) DEFAULT 'LOW';
ALTER TABLE campaign_logs ADD COLUMN IF NOT EXISTS account_used VARCHAR(100);
ALTER TABLE campaign_logs ADD COLUMN IF NOT EXISTS eligibility VARCHAR(20);

COMMENT ON COLUMN campaign_logs.delivery_id IS 'Unique delivery identifier for idempotency tracking';
COMMENT ON COLUMN campaign_logs.attempt_count IS 'Total number of send attempts for this delivery';
COMMENT ON COLUMN campaign_logs.last_attempt_at IS 'Timestamp of the most recent send attempt';
COMMENT ON COLUMN campaign_logs.next_attempt_at IS 'Earliest timestamp for next retry attempt';
COMMENT ON COLUMN campaign_logs.last_error IS 'Most recent error detail from dispatch';
COMMENT ON COLUMN campaign_logs.risk_level IS 'Risk level at dispatch time: LOW, MEDIUM, HIGH, CRITICAL';
COMMENT ON COLUMN campaign_logs.account_used IS 'Telegram session name that dispatched this message';
COMMENT ON COLUMN campaign_logs.eligibility IS 'Pre-dispatch eligibility: ELIGIBLE, RISKY, COOLDOWN, BLOCKED, CONTACTED, FAILED';

-- ─── New columns on leads ────────────────────────────────────────────────────

ALTER TABLE leads ADD COLUMN IF NOT EXISTS risk_score INT DEFAULT 0;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS last_contact_at TIMESTAMP;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS next_eligible_at TIMESTAMP;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS contact_cooldown_days INT DEFAULT 30;

COMMENT ON COLUMN leads.risk_score IS 'Outreach risk score (0-100): higher = riskier to contact';
COMMENT ON COLUMN leads.last_contact_at IS 'Timestamp of last outreach attempt to this lead';
COMMENT ON COLUMN leads.next_eligible_at IS 'Per-lead cooldown expiry: earliest next contact allowed';
COMMENT ON COLUMN leads.contact_cooldown_days IS 'Minimum days between outreach contacts (default 30)';

-- ─── New table: account_health ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS account_health (
    session_name          VARCHAR(100)  PRIMARY KEY,
    state                 VARCHAR(20)   NOT NULL DEFAULT 'HEALTHY',
    health_score          INT           NOT NULL DEFAULT 100,
    total_sends           INT           NOT NULL DEFAULT 0,
    total_failures        INT           NOT NULL DEFAULT 0,
    total_flood_waits     INT           NOT NULL DEFAULT 0,
    flood_wait_seconds_total INT        NOT NULL DEFAULT 0,
    last_flood_wait_at    TIMESTAMP,
    last_success_at       TIMESTAMP,
    last_error_at         TIMESTAMP,
    last_error_message    TEXT,
    cooldown_until        TIMESTAMP,
    state_changed_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE account_health IS 'Telegram account health state machine for outreach risk management';
COMMENT ON COLUMN account_health.state IS 'Account state: HEALTHY, DEGRADED, COOLDOWN, RESTRICTED, QUARANTINED, DISABLED';
COMMENT ON COLUMN account_health.health_score IS 'Numeric health score 0-100, synced with Redis health:{session_name}:score';

-- ─── New table: flood_wait_log ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS flood_wait_log (
    id              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    session_name    VARCHAR(100)  NOT NULL,
    method          VARCHAR(100)  NOT NULL DEFAULT 'unknown',
    wait_seconds    INT           NOT NULL,
    timestamp       TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE flood_wait_log IS 'Historical log of all FloodWait events for trend analysis and risk scoring';

-- ─── New table: outreach_metrics ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS outreach_metrics (
    id              SERIAL        PRIMARY KEY,
    metric_name     VARCHAR(100)  NOT NULL,
    metric_value    FLOAT         NOT NULL DEFAULT 0,
    labels          JSONB         NOT NULL DEFAULT '{}',
    recorded_at     TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE outreach_metrics IS 'Historical outreach metrics for observability dashboards and trend analysis';

-- ─── Indexes ─────────────────────────────────────────────────────────────────

-- campaign_logs indexes for outreach worker queries
CREATE INDEX IF NOT EXISTS idx_campaign_logs_delivery_id
    ON campaign_logs(delivery_id);

CREATE INDEX IF NOT EXISTS idx_campaign_logs_next_attempt
    ON campaign_logs(next_attempt_at)
    WHERE status IN ('pending', 'processing');

CREATE INDEX IF NOT EXISTS idx_campaign_logs_eligibility
    ON campaign_logs(eligibility)
    WHERE eligibility IS NOT NULL;

-- leads indexes for per-lead cooldown
CREATE INDEX IF NOT EXISTS idx_leads_next_eligible
    ON leads(next_eligible_at)
    WHERE next_eligible_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_leads_risk_score
    ON leads(risk_score)
    WHERE risk_score > 0;

CREATE INDEX IF NOT EXISTS idx_leads_last_contact
    ON leads(last_contact_at)
    WHERE last_contact_at IS NOT NULL;

-- account_health indexes
CREATE INDEX IF NOT EXISTS idx_account_health_state
    ON account_health(state);

-- flood_wait_log indexes for trend queries
CREATE INDEX IF NOT EXISTS idx_flood_wait_log_session
    ON flood_wait_log(session_name, timestamp);

CREATE INDEX IF NOT EXISTS idx_flood_wait_log_timestamp
    ON flood_wait_log(timestamp);

-- outreach_metrics indexes for dashboard queries
CREATE INDEX IF NOT EXISTS idx_outreach_metrics_name_time
    ON outreach_metrics(metric_name, recorded_at);

-- Retention policy helper: partition-friendly index for old metric cleanup
CREATE INDEX IF NOT EXISTS idx_outreach_metrics_recorded_at
    ON outreach_metrics(recorded_at);

-- ─── Done ────────────────────────────────────────────────────────────────────
