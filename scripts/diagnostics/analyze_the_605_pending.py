import psycopg2
from psycopg2.extras import RealDictCursor
import os

from dashboard import get_db_connection

def main():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Fetch active campaign id
    cur.execute("SELECT id FROM campaigns WHERE status = 'active' ORDER BY created_at DESC LIMIT 1")
    camp = cur.fetchone()
    if not camp:
        print("No active campaign")
        return

    camp_id = camp['id']

    # Get all 605 pending logs with lead details
    cur.execute("""
        SELECT cl.id as log_id, l.id as lead_id, l.channel_username, l.contact_username, l.is_group, l.member_count
        FROM campaign_logs cl
        JOIN leads l ON cl.lead_id = l.id
        WHERE cl.campaign_id = %s AND cl.status = 'pending'
    """, (camp_id,))
    pending_logs = cur.fetchall()

    total_pending = len(pending_logs)
    has_contact = [l for l in pending_logs if l['contact_username'] and l['contact_username'].strip()]
    no_contact = [l for l in pending_logs if not l['contact_username'] or not l['contact_username'].strip()]

    channels_count = sum(1 for l in pending_logs if not l['is_group'])
    groups_count = sum(1 for l in pending_logs if l['is_group'])

    print(f"Total Pending Logs: {total_pending}")
    print(f"  - Channels: {channels_count}")
    print(f"  - Groups: {groups_count}")
    print(f"  - Has Direct Outreach Contact Username (@username): {len(has_contact)} ({len(has_contact)*100.0/total_pending:.1f}%)")
    print(f"  - Missing Direct Contact Username: {len(no_contact)} ({len(no_contact)*100.0/total_pending:.1f}%)")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
