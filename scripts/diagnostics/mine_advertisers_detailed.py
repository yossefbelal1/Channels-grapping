import os
import re
import json
import psycopg2
from psycopg2.extras import RealDictCursor

# Connect to DB inside container or host
conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "postgres"),
    port=int(os.getenv("DB_PORT", "5432")),
    dbname=os.getenv("DB_NAME", "leadhunter_db"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", "leadhunter_pass")
)

cur = conn.cursor(cursor_factory=RealDictCursor)

# 1. Search keywords for ad exchange / marketing / managers
AD_KEYWORDS = [
    'تبادل', 'إعلاني', 'اعلاني', 'اعلان', 'إعلان', 'اعلانات', 'إعلانات',
    'مدير', 'مديرة', 'مسوق', 'مسوقة', 'مسؤول', 'مسؤولة',
    'دعاية', 'ترويج', 'سبونسر', 'sponsor', 'ads', 'marketing',
    'دينا', 'فاتن', 'هاجر', 'مايسة', 'ميساء', 'فريدا', 'فريدة', 'مختار',
    'منسق', 'منسقة', 'للتواصل الإعلاني', 'للتواصل الاعلاني', 'للإعلان', 'للاعلان'
]

print("=== Mining Ad Exchange & Marketer Contacts from Leads & Posts ===")

# Query 1: Extract from leads descriptions and contact_usernames
print("\n[1] Scanning `leads` table (8,334 channels)...")
cur.execute("""
    SELECT id, channel_username, member_count, description, contact_username, 
           whatsapp, email, website, marketplace_score, lead_score, tier, status
    FROM leads
    WHERE description ILIKE '%تبادل%'
       OR description ILIKE '%اعلان%'
       OR description ILIKE '%إعلان%'
       OR description ILIKE '%دعاية%'
       OR description ILIKE '%مسوق%'
       OR description ILIKE '%دينا%'
       OR description ILIKE '%فاتن%'
       OR description ILIKE '%هاجر%'
       OR description ILIKE '%مايسة%'
       OR description ILIKE '%فريد%'
       OR description ILIKE '%مختار%'
       OR description ILIKE '%marketing%'
       OR description ILIKE '%ads%'
       OR contact_username ILIKE '%ad%'
       OR contact_username ILIKE '%mark%'
       OR contact_username ILIKE '%tabad%'
       OR contact_username ILIKE '%dina%'
       OR contact_username ILIKE '%faten%'
       OR contact_username ILIKE '%hagar%'
       OR contact_username ILIKE '%mokhtar%';
""")
leads_results = cur.fetchall()
print(f"Found {len(leads_results)} matching leads with advertising/marketing signals.")

# Query 2: Extract from channel_posts (72,232 posts)
print("\n[2] Scanning `channel_posts` table (72,232 posts)...")
cur.execute("""
    SELECT channel_username, message_id, timestamp, message_text
    FROM channel_posts
    WHERE message_text ILIKE '%تبادل%'
       OR message_text ILIKE '%مدير تبادل%'
       OR message_text ILIKE '%مديرة تبادل%'
       OR message_text ILIKE '%مسؤول الاعلان%'
       OR message_text ILIKE '%مسؤولة الاعلان%'
       OR message_text ILIKE '%للتواصل والاعلان%'
       OR message_text ILIKE '%للاعلانات%'
       OR message_text ILIKE '%للإعلانات%'
       OR message_text ILIKE '%دينا%'
       OR message_text ILIKE '%فاتن%'
       OR message_text ILIKE '%هاجر%'
       OR message_text ILIKE '%مايسة%'
       OR message_text ILIKE '%فريدا%'
       OR message_text ILIKE '%مختار%'
    ORDER BY timestamp DESC
    LIMIT 1000;
""")
posts_results = cur.fetchall()
print(f"Found {len(posts_results)} matching posts mentioning advertising/names.")

# Regex patterns to extract usernames, names, phone numbers from text
USERNAME_REGEX = re.compile(r'(?:@|t\.me/)([a-zA-Z0-9_]{4,32})', re.IGNORECASE)
PHONE_REGEX = re.compile(r'(?:\+?\d{1,4}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,5}')

# Aggregation dictionary by contact username or person name
advertisers = {}

def add_contact(contact_user, name=None, role=None, channel=None, snippet=None, phone=None):
    if not contact_user:
        return
    cu = contact_user.lower().lstrip('@').replace('https://t.me/', '').replace('t.me/', '')
    # Filter junk bots / commands
    if cu.endswith('bot') or cu in ('joinchat', 'addlist', 'everyone', 'share', 'contact', 'admin'):
        return
        
    if cu not in advertisers:
        advertisers[cu] = {
            'username': f"@{cu}",
            'names': set(),
            'roles': set(),
            'channels': set(),
            'phones': set(),
            'snippets': []
        }
    
    if name:
        advertisers[cu]['names'].add(name)
    if role:
        advertisers[cu]['roles'].add(role)
    if channel:
        advertisers[cu]['channels'].add(f"@{channel.lstrip('@')}")
    if phone:
        advertisers[cu]['phones'].add(phone)
    if snippet and len(advertisers[cu]['snippets']) < 3:
        advertisers[cu]['snippets'].append(snippet[:200].strip())

# Process leads
for row in leads_results:
    desc = row.get('description') or ''
    cu = row.get('contact_username')
    ch = row.get('channel_username')
    wa = row.get('whatsapp')
    
    # Extract any context around names or roles
    for name in ['دينا', 'فاتن', 'هاجر', 'مايسة', 'فريدا', 'فريدة', 'مختار', 'سارة', 'نور', 'ياسمين', 'ريم', 'منة']:
        if name in desc:
            add_contact(cu, name=name, role="مسؤول/مدير تبادل إعلاني", channel=ch, snippet=desc, phone=wa)
            
    # Check for general keywords
    for kw in ['تبادل', 'إعلان', 'اعلان', 'دعاية', 'تسويق']:
        if kw in desc:
            add_contact(cu, role="إعلانات وتبادل", channel=ch, snippet=desc, phone=wa)
            
    # Also find all @mentions in description
    mentions = USERNAME_REGEX.findall(desc)
    for m in mentions:
        if any(w in desc.lower() for w in ['اعلان', 'إعلان', 'تبادل', 'تواصل', 'ادمن', 'admin', 'ads']):
            add_contact(m, channel=ch, snippet=desc, phone=wa)

# Process posts
for row in posts_results:
    text = row.get('message_text') or ''
    ch = row.get('channel_username')
    mentions = USERNAME_REGEX.findall(text)
    
    # Extract roles and names in text
    detected_name = None
    for name in ['دينا', 'فاتن', 'هاجر', 'مايسة', 'ميساء', 'فريدا', 'فريدة', 'مختار', 'سارة', 'أحمد', 'محمد', 'كريم']:
        if name in text:
            detected_name = name
            break
            
    detected_role = "مسؤول تبادل إعلاني / معلن" if ('تبادل' in text or 'اعلان' in text or 'إعلان' in text) else "جهة تواصل"
    
    for m in mentions:
        add_contact(m, name=detected_name, role=detected_role, channel=ch, snippet=text)

print(f"\n[+] Total unique advertisers / ad managers extracted: {len(advertisers)}")

# Format and sort by importance (channels count & snippets)
sorted_ads = sorted(
    advertisers.values(),
    key=lambda x: (len(x['channels']), len(x['snippets']), len(x['names'])),
    reverse=True
)

output_data = []
for item in sorted_ads:
    output_data.append({
        'username': item['username'],
        'names': list(item['names']),
        'roles': list(item['roles']),
        'channels': list(item['channels'])[:5],
        'phones': list(item['phones']),
        'sample_snippet': item['snippets'][0] if item['snippets'] else ''
    })

# Save JSON and print top 50
json_path = os.getenv("OUTPUT_JSON", "/app/advertisers_mined.json")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(output_data, f, ensure_ascii=False, indent=2)

print(f"\nSaved full data to {json_path}")
print("=" * 70)
print(f"Top 50 Extracted Ad Managers & Advertisers (Total Found: {len(output_data)}):")
print("=" * 70 + "\n")
for i, ad in enumerate(output_data[:50], 1):
    names_str = ", ".join(ad['names']) if ad['names'] else "غير محدد"
    roles_str = ", ".join(ad['roles']) if ad['roles'] else "معلن / تبادل"
    channels_str = ", ".join(ad['channels']) if ad['channels'] else "-"
    phones_str = f" | هاتف/واتساب: {', '.join(ad['phones'])}" if ad['phones'] else ""
    print(f"{i}. {ad['username']} | الاسم: {names_str} | الدور: {roles_str}{phones_str}")
    print(f"   القنوات المرتبطة: {channels_str}")
    if ad['sample_snippet']:
        clean_snip = ad['sample_snippet'].replace('\n', ' ')
        print(f"   البيان/السياق: {clean_snip[:140]}...")
    print("-" * 70)
