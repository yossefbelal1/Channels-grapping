-- Migration v9: Auto-Reply Engine
ALTER TABLE campaigns 
ADD COLUMN IF NOT EXISTS auto_reply_enabled BOOLEAN DEFAULT TRUE,
ADD COLUMN IF NOT EXISTS auto_reply_message_text TEXT DEFAULT NULL,
ADD COLUMN IF NOT EXISTS auto_reply_media_path VARCHAR(255) DEFAULT NULL;

ALTER TABLE campaign_logs 
ADD COLUMN IF NOT EXISTS auto_reply_sent BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS auto_reply_sent_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NULL,
ADD COLUMN IF NOT EXISTS auto_reply_error TEXT DEFAULT NULL,
ADD COLUMN IF NOT EXISTS telegram_user_id BIGINT DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_campaign_logs_telegram_user_id ON campaign_logs(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_campaign_logs_auto_reply_sent ON campaign_logs(auto_reply_sent);
