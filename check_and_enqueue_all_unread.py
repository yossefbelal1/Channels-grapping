import os
import uuid
from psycopg2.extras import RealDictCursor
from dashboard import get_db_connection

def main():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 1. Get active campaign
    cur.execute("SELECT id FROM campaigns WHERE status = 'active' ORDER BY created_at DESC LIMIT 1")
    row = cur.fetchone()
    if not row:
        print("No active campaign found!")
        return

    active_campaign_id = row['id']
    print(f"Active Campaign ID: {active_campaign_id}")

    # 2. Check all eligible leads in leads table
    cur.execute("""
        SELECT l.id, l.channel_username, l.contact_username
        FROM leads l
        WHERE l.status != 'rejected'
          AND l.contact_username IS NOT NULL
          AND l.contact_username != ''
          AND l.member_count > 0
          AND (l.description IS NULL OR l.description NOT LIKE 'Blacklisted entity%%')
          AND (l.description IS NULL OR l.description NOT LIKE 'Entity does not exist%%')
    """)
    eligible_leads = cur.fetchall()
    print(f"Total Eligible Leads in database: {len(eligible_leads)}")

    # 3. Check how many are currently in campaign_logs
    cur.execute("SELECT lead_id FROM campaign_logs WHERE campaign_id = %s", (active_campaign_id,))
    enqueued_lead_ids = {r['lead_id'] for r in cur.fetchall()}
    print(f"Currently Enqueued Leads in Campaign: {len(enqueued_lead_ids)}")

    # 4. Find unqueued leads
    unqueued = [l for l in eligible_leads if l['id'] not in enqueued_lead_ids]
    print(f"Unqueued Leads count: {len(unqueued)}")

    # Enqueue any unqueued leads!
    if unqueued:
        print(f"\nEnqueuing {len(unqueued)} unqueued leads into active campaign...")
        for l in unqueued:
            log_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO campaign_logs (id, campaign_id, lead_id, status)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (log_id, active_campaign_id, l['id'], 'pending'))
        conn.commit()
        print(f"✓ Enqueued {len(unqueued)} leads successfully!")
    else:
        print("✓ All eligible leads are ALREADY enqueued in the campaign!")

    # 5. Check campaign stats summary
    cur.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN status = 'sent' THEN 1 END) as sent,
            COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
            COUNT(CASE WHEN status = 'skipped' THEN 1 END) as skipped,
            COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending
        FROM campaign_logs
        WHERE campaign_id = %s
    """, (active_campaign_id,))
    stats = cur.fetchone()
    print("\nUpdated Active Campaign Summary:")
    print(f"  Total Recipients: {stats['total']}")
    print(f"  Sent: {stats['sent']}")
    print(f"  Failed: {stats['failed']}")
    print(f"  Skipped (Deduplicated): {stats['skipped']}")
    print(f"  Pending: {stats['pending']}")
    print(f"  Sum (Sent+Failed+Skipped+Pending): {stats['sent'] + stats['failed'] + stats['skipped'] + stats['pending']}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
