import os
import re
import json
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "postgres"),
    port=int(os.getenv("DB_PORT", "5432")),
    dbname=os.getenv("DB_NAME", "leadhunter_db"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", "leadhunter_pass")
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 80)
print("SEARCHING FOR MARKETER: 'ناهد' (Nahed) ACROSS DATABASE")
print("=" * 80)

# Search channel_posts
cur.execute("""
    SELECT channel_username, message_id, timestamp, message_text 
    FROM channel_posts 
    WHERE message_text ~* '(ناهد|nahed)'
    ORDER BY timestamp DESC;
""")
nahed_posts = cur.fetchall()
print(f"Found {len(nahed_posts)} posts mentioning 'ناهد' or 'nahed'.")

# Search leads
cur.execute("""
    SELECT channel_username, description, contact_username 
    FROM leads 
    WHERE description ~* '(ناهد|nahed)' 
       OR contact_username ~* 'nahed';
""")
nahed_leads = cur.fetchall()
print(f"Found {len(nahed_leads)} leads mentioning 'ناهد' or 'nahed'.")

# Search seen_channels
try:
    cur.execute("SELECT username, title FROM seen_channels WHERE username ~* 'nahed' OR title ~* 'ناهد';")
    nahed_seen = cur.fetchall()
    print(f"Found {len(nahed_seen)} seen channels.")
except Exception:
    conn.rollback()
    nahed_seen = []

USERNAME_REGEX = re.compile(r'(?:@|https?://t\.me/|t\.me/)([a-zA-Z0-9_]{4,32})', re.IGNORECASE)

results = []

for p in nahed_posts:
    text = p['message_text'] or ''
    ch = p['channel_username'] or ''
    mentions = USERNAME_REGEX.findall(text)
    results.append({
        'source': f"Post in @{ch}",
        'mentions': mentions,
        'snippet': text[:200]
    })

for l in nahed_leads:
    desc = l['description'] or ''
    cu = l['contact_username'] or ''
    ch = l['channel_username'] or ''
    mentions = USERNAME_REGEX.findall(desc)
    if cu:
        mentions.append(cu)
    results.append({
        'source': f"Lead @{ch}",
        'mentions': list(set(mentions)),
        'snippet': desc[:200]
    })

for s in nahed_seen:
    results.append({
        'source': f"Seen Channel @{s['username']}",
        'mentions': [s['username']],
        'snippet': s.get('title', '')
    })

print(f"\nTotal extraction records: {len(results)}")
for r in results:
    print(f"\n--- {r['source']} ---")
    print(f"Mentions: {r['mentions']}")
    print(f"Snippet: {r['snippet']}")

with open('/app/nahed_search_results.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
