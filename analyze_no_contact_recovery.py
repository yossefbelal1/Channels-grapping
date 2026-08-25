"""
Analyze the descriptions and posts of channels that failed with "No contact"
to see why contact extraction failed and how many contacts we can recover.
"""
import psycopg2
import os
import re
import sys
from psycopg2.extras import RealDictCursor

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

    cur.execute("SELECT id FROM campaigns WHERE id::text LIKE %s LIMIT 1", (CAMPAIGN_ID_PREFIX + '%',))
    row = cur.fetchone()
    if not row:
        print("Campaign not found!")
        return
    campaign_id = row['id']

    cur.execute("""
        SELECT l.id as lead_id, l.channel_username, l.description, l.member_count, cl.id as log_id
        FROM campaign_logs cl
        JOIN leads l ON l.id = cl.lead_id
        WHERE cl.campaign_id = %s
          AND cl.status IN ('failed', 'FAILED', 'error', 'ERROR')
          AND cl.error_message ILIKE '%%No owner or admin contact%%'
        ORDER BY l.member_count DESC NULLS LAST
    """, (campaign_id,))
    leads = cur.fetchall()
    print(f"Total no-contact failed leads: {len(leads)}")

    # Test improved regex on description and posts
    recovered = 0
    sample_recovered = []

    # Regex for t.me links and @mentions
    tme_regex = re.compile(r'(?:https?://)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]{4,32})', re.IGNORECASE)
    at_regex = re.compile(r'@([a-zA-Z0-9_]{4,32})', re.IGNORECASE)

    skip_names = {
        'joinchat', 'addstickers', 'share', 'channel', 'vip', 'forex', 'crypto',
        'trading', 'signals', 'bot', 'adminbot', 'group', 'link', 'official'
    }

    for lead in leads:
        lead_id = lead['lead_id']
        username = lead['channel_username'] or ''
        desc = lead['description'] or ''

        # Get recent posts
        cur.execute("""
            SELECT message_text FROM channel_posts
            WHERE channel_username = %s
            ORDER BY timestamp DESC
            LIMIT 15
        """, (username,))
        posts = [p['message_text'] or '' for p in cur.fetchall()]
        all_text = desc + "\n" + "\n".join(posts)

        # Extract all t.me links and @mentions
        found_usernames = set()
        for m in tme_regex.finditer(all_text):
            u = m.group(1)
            if u.lower() != username.lower() and u.lower() not in skip_names and not u.startswith('+'):
                found_usernames.add(u)

        for m in at_regex.finditer(all_text):
            u = m.group(1)
            if u.lower() != username.lower() and u.lower() not in skip_names:
                found_usernames.add(u)

        if found_usernames:
            recovered += 1
            if len(sample_recovered) < 25:
                sample_recovered.append({
                    'channel': username,
                    'members': lead['member_count'],
                    'found': list(found_usernames)[:3],
                    'desc_snippet': desc[:80]
                })

    print(f"\nPotential recovered contacts from DB text: {recovered} / {len(leads)} ({recovered/len(leads)*100:.1f}%)")
    print("\nSample recovered contacts:")
    for s in sample_recovered:
        print(f"  Channel: @{s['channel']:25s} ({s['members'] or 0:,} members) -> Candidates: {s['found']}")

    conn.close()

if __name__ == "__main__":
    main()
