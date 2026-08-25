"""
Auto-enqueue all valid contacts into the active campaign.
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "dbname": os.getenv("DB_NAME", "leadhunter_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "postgres"),
}

def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT id FROM campaigns WHERE status = 'active' ORDER BY created_at DESC LIMIT 1")
    active_camp = cur.fetchone()
    if not active_camp:
        print("No active campaign found!")
        conn.close()
        return

    cid = active_camp['id']
    print(f"Active Campaign ID: {cid}")

    # Check how many leads will be added
    cur.execute("""
        SELECT COUNT(*) as eligible_count
        FROM leads l
        WHERE l.contact_username IS NOT NULL
          AND l.contact_username != ''
          AND LOWER(l.contact_username) NOT IN ('addlist', 'share', 'joinchat', 'setlanguage', 'proxy', 'socks', 'c', 's', 'm', 'i')
          AND (l.description IS NULL OR (l.description NOT LIKE 'Blacklisted entity%%' AND l.description NOT LIKE 'Entity does not exist%%'))
          AND l.id NOT IN (SELECT lead_id FROM campaign_logs WHERE campaign_id = %s)
    """, (cid,))
    row = cur.fetchone()
    to_add = row['eligible_count']
    print(f"Found {to_add} eligible leads with valid contacts to enqueue into campaign.")

    # Insert into campaign_logs
    cur.execute("""
        INSERT INTO campaign_logs (id, campaign_id, lead_id, status)
        SELECT gen_random_uuid(), %s, l.id, 'pending'
        FROM leads l
        WHERE l.contact_username IS NOT NULL
          AND l.contact_username != ''
          AND LOWER(l.contact_username) NOT IN ('addlist', 'share', 'joinchat', 'setlanguage', 'proxy', 'socks', 'c', 's', 'm', 'i')
          AND (l.description IS NULL OR (l.description NOT LIKE 'Blacklisted entity%%' AND l.description NOT LIKE 'Entity does not exist%%'))
          AND l.id NOT IN (SELECT lead_id FROM campaign_logs WHERE campaign_id = %s)
        ON CONFLICT (id) DO NOTHING
    """, (cid, cid))
    inserted = cur.rowcount
    conn.commit()

    print(f"✅ Successfully enqueued {inserted} leads into campaign!")

    # Show new summary
    cur.execute("""
        SELECT 
            COUNT(cl.id) as total_recipients,
            COUNT(CASE WHEN cl.status = 'sent' THEN 1 END) as sent,
            COUNT(CASE WHEN cl.status = 'failed' THEN 1 END) as failed,
            COUNT(CASE WHEN cl.status = 'skipped' THEN 1 END) as skipped,
            COUNT(CASE WHEN cl.status = 'pending' THEN 1 END) as pending
        FROM campaign_logs cl
        WHERE cl.campaign_id = %s
    """, (cid,))
    stats = cur.fetchone()

    print("\n" + "="*50)
    print("📊 UPDATED CAMPAIGN STATUS:")
    print(f"  • Total Recipients: {stats['total_recipients']}")
    print(f"  • Pending (Ready to send): {stats['pending']}")
    print(f"  • Sent (Completed): {stats['sent']}")
    print(f"  • Skipped (Duplicates): {stats['skipped']}")
    print(f"  • Failed (Unreachable): {stats['failed']}")
    print("="*50)

    conn.close()

if __name__ == "__main__":
    main()
