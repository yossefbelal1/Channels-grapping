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
print("EXHAUSTIVE NAHED INVESTIGATOR - ALL TABLES & NETWORK CROSS-REFERENCE")
print("=" * 80)

KNOWN_NETWORK = [
    'rahma4565', 'adsazza', 'mariam_ads', 'joee_ads', 'maysa_ads', 'adprofx',
    'adssafwat', 'emanads000', 'adssalmaa', 'farida_ads', 'mohamed_ads97',
    'asmaaa_ads', 'myaaaarrrr', 'faridaads', 'mairaads', 'lina_bnm',
    'mai_promoter', 'abdo0o0o0oo', 'mohammedads33', 'aesygul', 'maha2210',
    'fatenexchange', 'maryamads1', 'elitetradersad', 'elsaidd22', 'adswift',
    'lamar_ads', 'mokhtarr1', 'hayamad2j', 'jamilaads', 'sarah_ads',
    'uniqads2', 'meromero3131', 'mayar_medhat1012', 'nancy_ads1',
    'abou_yaqoub', 'emaads', 'stateuntied_ads', 'khaled_ads', 'malak_ads22',
    'maya_ads1', 'node231', 'dododede23', 'malaaaakads', 'mohamedben392',
    'ggfigt', 'zeyad3112', 'nonaads', 'adsonlyf'
]

# Query 1: Search `channel_posts` across all partitions
cur.execute("""
    SELECT channel_username, message_id, timestamp, message_text 
    FROM channel_posts 
    WHERE message_text ~* '(ناهد|نـاهد|ناهـد|ناهِد|نهاد|نـهاد|nahed|nahaed|nahid|nehad|nihad|naehed|nonaads)'
    ORDER BY timestamp DESC;
""")
post_matches = cur.fetchall()
print(f"Total post matches for Nahed/Variants/Nona: {len(post_matches)}")

# Query 2: Search `leads`
cur.execute("""
    SELECT * FROM leads 
    WHERE description ~* '(ناهد|نـاهد|ناهـد|ناهِد|نهاد|نـهاد|nahed|nahaed|nahid|nehad|nihad|naehed|nonaads)'
       OR contact_username ~* '(ناهد|نـاهد|ناهـد|ناهِد|نهاد|نـهاد|nahed|nahaed|nahid|nehad|nihad|naehed|nonaads)'
       OR channel_username ~* '(ناهد|نـاهد|ناهـد|ناهِد|نهاد|نـهاد|nahed|nahaed|nahid|nehad|nihad|naehed|nonaads)';
""")
lead_matches = cur.fetchall()
print(f"Total lead matches for Nahed/Variants/Nona: {len(lead_matches)}")

# Query 3: Search for any contacts in posts where known network advertisers post or where ad phrases occur
cur.execute("""
    SELECT channel_username, message_id, timestamp, message_text 
    FROM channel_posts 
    WHERE message_text ~* '(للإعلان|للحجز والإعلان|للتواصل الإعلاني|حجز إعلانات|تبادل إعلاني|تبادل اعلاني|free ad exchange|ads:)'
    ORDER BY timestamp DESC LIMIT 500;
""")
ad_context_posts = cur.fetchall()
print(f"Ad context posts sampled: {len(ad_context_posts)}")

output = {
    'post_matches': [dict(p) for p in post_matches],
    'lead_matches': [dict(l) for l in lead_matches],
    'ad_context_posts': [dict(a) for a in ad_context_posts[:50]]
}

with open('/app/nahed_exhaustive_investigation.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2, default=str)

print("Saved exhaustive investigation to /app/nahed_exhaustive_investigation.json")
