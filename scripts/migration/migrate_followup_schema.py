"""
Database Migration: Add follow-up support to campaigns and campaign_logs tables.
"""
import psycopg2
import os
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "dbname": os.getenv("DB_NAME", "leadhunter"),
    "user": os.getenv("DB_USER", "leadhunter"),
    "password": os.getenv("DB_PASSWORD", "leadhunter"),
}

def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    print("Running database migration for Follow-up Campaign System...")

    # 1. Add follow-up fields to campaigns table
    cur.execute("""
        ALTER TABLE campaigns 
        ADD COLUMN IF NOT EXISTS followup_message_text TEXT,
        ADD COLUMN IF NOT EXISTS followup_media_path VARCHAR(255),
        ADD COLUMN IF NOT EXISTS followup_enabled BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS followup_delay_days INT DEFAULT 4;
    """)

    # 2. Add follow-up tracking fields to campaign_logs table
    cur.execute("""
        ALTER TABLE campaign_logs
        ADD COLUMN IF NOT EXISTS followup_status VARCHAR(20) DEFAULT NULL,
        ADD COLUMN IF NOT EXISTS followup_sent_at TIMESTAMP DEFAULT NULL,
        ADD COLUMN IF NOT EXISTS followup_error_message TEXT,
        ADD COLUMN IF NOT EXISTS user_replied BOOLEAN DEFAULT FALSE;
    """)

    # 3. Create index for fast follow-up querying
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_campaign_logs_followup_status ON campaign_logs(followup_status);
        CREATE INDEX IF NOT EXISTS idx_campaign_logs_sent_at ON campaign_logs(sent_at);
    """)

    conn.commit()
    print("✅ Database migration completed successfully!")

    # Show columns verification
    cur.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'campaign_logs' AND column_name LIKE 'followup%' OR column_name = 'user_replied';
    """)
    rows = cur.fetchall()
    print("\nVerified columns in campaign_logs:")
    for r in rows:
        print(f"  - {r[0]} ({r[1]})")

    conn.close()

if __name__ == "__main__":
    main()
