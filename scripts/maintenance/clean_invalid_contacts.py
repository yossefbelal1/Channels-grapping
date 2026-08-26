"""
Inspect and clean invalid non-user contact usernames in leads and campaign_logs:
1. Clean keywords like 'addlist', 'share', 'joinchat', 'c', 's', 'addstickers', 'setlanguage'.
2. Reset any campaign_logs for those invalid contacts to pending with contact_username = NULL (or re-extract).
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

INVALID_USERNAMES = [
    'addlist', 'addstickers', 'share', 'joinchat', 'setlanguage', 'proxy', 'socks',
    'c', 's', 'm', 'i', 'bot', 'adminbot', 'channelbot', 'user'
]

def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Check for invalid contacts in leads table
    cur.execute("""
        SELECT id, channel_username, contact_username
        FROM leads
        WHERE LOWER(contact_username) = ANY(%s)
           OR contact_username ILIKE 'addlist%%'
           OR contact_username ILIKE 'joinchat%%'
    """, (INVALID_USERNAMES,))
    invalid_leads = cur.fetchall()

    print(f"Found {len(invalid_leads)} leads with invalid non-user contact usernames:")
    for l in invalid_leads:
        print(f"  - @{l['channel_username']} -> Invalid contact: @{l['contact_username']}")
        
        # Clean from leads
        cur.execute("UPDATE leads SET contact_username = NULL WHERE id = %s", (l['id'],))
        # Update in campaign_logs
        cur.execute("""
            UPDATE campaign_logs
            SET status = 'failed', error_message = 'No owner or admin contact username resolved for this channel'
            WHERE lead_id = %s AND (status = 'pending' OR status = 'failed')
        """, (l['id'],))

    conn.commit()
    print(f"Cleaned {len(invalid_leads)} invalid leads successfully!")

    # Check campaign logs status
    cur.execute("""
        SELECT status, COUNT(*) as cnt
        FROM campaign_logs
        GROUP BY status
        ORDER BY cnt DESC
    """)
    print("\n=== CURRENT CAMPAIGN LOGS STATUS ===")
    for r in cur.fetchall():
        print(f"  {r['status']:10s}: {r['cnt']}")

    conn.close()

if __name__ == "__main__":
    main()
