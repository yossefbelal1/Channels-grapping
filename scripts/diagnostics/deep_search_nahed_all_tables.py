import os
import re
import json
import glob
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
print("DEEP EXHAUSTIVE DATA MINING FOR 'NAHED / ناهد' & VARIANTS")
print("=" * 80)

# Check all tables in the database
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public';
""")
tables = [row['table_name'] for row in cur.fetchall()]
print(f"Found database tables: {tables}")

# Define all regex variants
NAHED_PATTERNS = [
    r'ناهد', r'نـاهد', r'ناهـد', r'ناهِد', r'نهاد', r'نـهاد',
    r'nahed', r'nahaed', r'nahid', r'nehad', r'nihad', r'naehed', r'nahd', r'nhed'
]
COMBINED_NAHED_REGEX = '|'.join(NAHED_PATTERNS)

AD_CONTEXT_TERMS = [
    r'ads?', r'advertising', r'advertiser', r'إعلان', r'اعلانات', r'للإعلان', r'الإعلان',
    r'معلن', r'معلنة', r'تداول', r'فوركس', r'forex', r'trading', r'crypto',
    r'للإعلان تواصل', r'للحجز والإعلان', r'للتواصل الإعلاني', r'للتواصل الاعلاني',
    r'حجز إعلانات', r'تبادل إعلاني', r'تبادل اعلاني', r'تبادل نشر'
]
COMBINED_AD_REGEX = '|'.join(AD_CONTEXT_TERMS)

results_by_source = []

# 1. Search in `leads`
if 'leads' in tables:
    print("\n[1] Searching `leads` table...")
    cur.execute(f"""
        SELECT * FROM leads 
        WHERE description ~* '{COMBINED_NAHED_REGEX}'
           OR contact_username ~* '{COMBINED_NAHED_REGEX}'
           OR channel_username ~* '{COMBINED_NAHED_REGEX}';
    """)
    leads_rows = cur.fetchall()
    print(f"Found {len(leads_rows)} leads matching Nahed variants.")
    for r in leads_rows:
        results_by_source.append({
            'source_table': 'leads',
            'channel_username': r.get('channel_username'),
            'contact_username': r.get('contact_username'),
            'description': r.get('description'),
            'member_count': r.get('member_count'),
            'raw': dict(r)
        })

# 2. Search in `channel_posts`
if 'channel_posts' in tables:
    print("\n[2] Searching `channel_posts` table...")
    cur.execute(f"""
        SELECT * FROM channel_posts 
        WHERE message_text ~* '{COMBINED_NAHED_REGEX}';
    """)
    posts_rows = cur.fetchall()
    print(f"Found {len(posts_rows)} posts matching Nahed variants.")
    for r in posts_rows:
        results_by_source.append({
            'source_table': 'channel_posts',
            'channel_username': r.get('channel_username'),
            'message_id': r.get('message_id'),
            'timestamp': str(r.get('timestamp')),
            'message_text': r.get('message_text'),
            'raw': dict(r)
        })

# 3. Search in `seen_channels`
if 'seen_channels' in tables:
    print("\n[3] Searching `seen_channels` table...")
    try:
        cur.execute(f"""
            SELECT * FROM seen_channels 
            WHERE username ~* '{COMBINED_NAHED_REGEX}'
               OR title ~* '{COMBINED_NAHED_REGEX}'
               OR description ~* '{COMBINED_NAHED_REGEX}';
        """)
        seen_rows = cur.fetchall()
        print(f"Found {len(seen_rows)} seen_channels matching Nahed variants.")
        for r in seen_rows:
            results_by_source.append({
                'source_table': 'seen_channels',
                'username': r.get('username'),
                'title': r.get('title'),
                'raw': dict(r)
            })
    except Exception as e:
        conn.rollback()
        print(f"Error querying seen_channels: {e}")

# 4. Search in `channel_graph`
if 'channel_graph' in tables:
    print("\n[4] Searching `channel_graph` table...")
    try:
        cur.execute(f"""
            SELECT * FROM channel_graph 
            WHERE source_channel ~* '{COMBINED_NAHED_REGEX}'
               OR target_channel ~* '{COMBINED_NAHED_REGEX}'
               OR context ~* '{COMBINED_NAHED_REGEX}';
        """)
        graph_rows = cur.fetchall()
        print(f"Found {len(graph_rows)} channel_graph rows matching Nahed variants.")
        for r in graph_rows:
            results_by_source.append({
                'source_table': 'channel_graph',
                'source_channel': r.get('source_channel'),
                'target_channel': r.get('target_channel'),
                'raw': dict(r)
            })
    except Exception as e:
        conn.rollback()
        print(f"Error querying channel_graph: {e}")

# 5. Search in `group_metrics`
if 'group_metrics' in tables:
    print("\n[5] Searching `group_metrics` table...")
    try:
        cur.execute(f"""
            SELECT * FROM group_metrics 
            WHERE channel_username ~* '{COMBINED_NAHED_REGEX}'
               OR top_posters::text ~* '{COMBINED_NAHED_REGEX}';
        """)
        metrics_rows = cur.fetchall()
        print(f"Found {len(metrics_rows)} group_metrics rows matching.")
        for r in metrics_rows:
            results_by_source.append({
                'source_table': 'group_metrics',
                'raw': dict(r)
            })
    except Exception as e:
        conn.rollback()
        print(f"Error querying group_metrics: {e}")

# 6. Search in `seed_channels`
if 'seed_channels' in tables:
    print("\n[6] Searching `seed_channels` table...")
    try:
        cur.execute(f"""
            SELECT * FROM seed_channels 
            WHERE channel_username ~* '{COMBINED_NAHED_REGEX}'
               OR notes ~* '{COMBINED_NAHED_REGEX}';
        """)
        seed_rows = cur.fetchall()
        print(f"Found {len(seed_rows)} seed_channels rows matching.")
        for r in seed_rows:
            results_by_source.append({
                'source_table': 'seed_channels',
                'raw': dict(r)
            })
    except Exception as e:
        conn.rollback()
        print(f"Error querying seed_channels: {e}")

print(f"\n[+] Total records collected across DB: {len(results_by_source)}")

with open('/app/nahed_raw_db_matches.json', 'w', encoding='utf-8') as f:
    json.dump(results_by_source, f, ensure_ascii=False, indent=2, default=str)

print("Saved raw matches to /app/nahed_raw_db_matches.json")
