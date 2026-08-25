"""
Fix campaign failures:
1. Reset 'Too many requests' failures back to pending
2. Export all channels with no contact_username as CSV for manual outreach
"""
import asyncio
import sys
import os
import csv
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "dbname": os.getenv("DB_NAME", "leadhunter"),
    "user": os.getenv("DB_USER", "leadhunter"),
    "password": os.getenv("DB_PASSWORD", "leadhunter"),
}

CAMPAIGN_ID_PREFIX = "30d91eeb"

def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Find campaign
    cur.execute("SELECT id FROM campaigns WHERE id::text LIKE %s LIMIT 1", (CAMPAIGN_ID_PREFIX + '%',))
    row = cur.fetchone()
    if not row:
        print("Campaign not found!")
        return
    campaign_id = row['id']
    print(f"Campaign ID: {campaign_id}")

    # ── Step 1: Reset 'Too many requests' back to pending ──────────────────
    cur.execute("""
        UPDATE campaign_logs
        SET status = 'pending', error_message = NULL, sent_at = NULL
        WHERE campaign_id = %s
          AND status IN ('failed', 'FAILED', 'error', 'ERROR')
          AND error_message ILIKE '%%too many requests%%'
    """, (campaign_id,))
    reset_count = cur.rowcount
    conn.commit()
    print(f"\n✅ Reset {reset_count} 'Too many requests' failures → pending (will retry)")

    # ── Step 2: Show current status breakdown ──────────────────────────────
    cur.execute("""
        SELECT status, COUNT(*) as cnt
        FROM campaign_logs
        WHERE campaign_id = %s
        GROUP BY status
        ORDER BY cnt DESC
    """, (campaign_id,))
    print("\n=== CURRENT STATUS BREAKDOWN ===")
    for r in cur.fetchall():
        print(f"  {r['status']:10s}: {r['cnt']}")

    # ── Step 3: Export channels with no contact (255 records) as CSV ───────
    cur.execute("""
        SELECT
            l.channel_username,
            l.member_count,
            l.description,
            l.lead_score,
            l.tier,
            l.contact_username,
            cl.error_message
        FROM campaign_logs cl
        JOIN leads l ON l.id = cl.lead_id
        WHERE cl.campaign_id = %s
          AND cl.status IN ('failed', 'FAILED', 'error', 'ERROR')
          AND cl.error_message ILIKE '%%No owner or admin contact%%'
        ORDER BY l.member_count DESC NULLS LAST
    """, (campaign_id,))
    no_contact_rows = cur.fetchall()

    output_csv = "/app/no_contact_channels.csv"
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['channel_username', 'telegram_link', 'member_count', 'lead_score', 'tier', 'description'])
        for r in no_contact_rows:
            username = r['channel_username'] or ''
            link = f"https://t.me/{username}" if username else ''
            writer.writerow([
                username,
                link,
                r['member_count'] or 0,
                r['lead_score'] or 0,
                r['tier'] or '',
                (r['description'] or '')[:100]
            ])

    print(f"\n✅ Exported {len(no_contact_rows)} no-contact channels to: {output_csv}")

    # Print top 30 no-contact channels
    print(f"\n=== TOP NO-CONTACT CHANNELS (biggest, {len(no_contact_rows)} total) ===")
    for i, r in enumerate(no_contact_rows[:30], 1):
        username = r['channel_username'] or 'unknown'
        members = r['member_count'] or 0
        score = r['lead_score'] or 0
        link = f"t.me/{username}"
        print(f"  {i:2d}. @{username:35s} | {members:7,} members | score={score} | {link}")

    # ── Step 4: Export also invalid username failures ───────────────────────
    cur.execute("""
        SELECT
            l.channel_username,
            l.member_count,
            l.contact_username,
            cl.error_message
        FROM campaign_logs cl
        JOIN leads l ON l.id = cl.lead_id
        WHERE cl.campaign_id = %s
          AND cl.status IN ('failed', 'FAILED', 'error', 'ERROR')
          AND cl.error_message NOT ILIKE '%%No owner or admin contact%%'
          AND cl.error_message NOT ILIKE '%%too many%%'
          AND cl.error_message NOT ILIKE '%%write in this chat%%'
        ORDER BY l.member_count DESC NULLS LAST
        LIMIT 100
    """, (campaign_id,))
    bad_username_rows = cur.fetchall()
    print(f"\n=== BAD/DELETED USERNAMES ({len(bad_username_rows)} shown) ===")
    for r in bad_username_rows[:20]:
        username = r['channel_username'] or '?'
        contact = r['contact_username'] or '?'
        err = (r['error_message'] or '')[:60]
        print(f"  Channel: @{username} | Contact tried: @{contact} | Error: {err}")

    conn.close()
    print("\n✅ Done! Next steps:")
    print(f"  1. {reset_count} 'Too many requests' resets done → they'll auto-retry")
    print(f"  2. {len(no_contact_rows)} no-contact channels saved to {output_csv}")
    print("  3. Download the CSV: scp root@167.233.246.102:/tmp/no_contact_channels.csv .")

if __name__ == "__main__":
    main()
