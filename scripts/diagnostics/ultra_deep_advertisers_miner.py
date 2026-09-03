import os
import re
import json
import urllib.parse
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

print("=" * 80)
print("ULTRA-DEEP MINING: ALL TELEGRAM AD AGENCIES, MEDIA BUYERS, EXCHANGES & PROMOTERS")
print("=" * 80)

# Comprehensive multilingual keywords
KEYWORDS = [
    'ad exchange', 'free ad exchange', 'ad agency', 'ads agency', 'media buyer',
    'media buying', 'growth agency', 'channel growth', 'promotion & growth',
    'promotion and growth', 'followers • views • engagement', 'traffic agency',
    'telegram ads', 'telegram marketing', 'channel promotion', 'crypto ads',
    'forex ads', 'trading ads', 'sponsor', 'sponsoring', 'advertiser', 'ad manager',
    'تبادل إعلاني', 'تبادل اعلاني', 'تبادل نشر', 'تبادل قنوات', 'نشر وتبادل',
    'مدير إعلانات', 'مديرة إعلانات', 'مدير اعلانات', 'مديرة اعلانات',
    'مسؤول إعلانات', 'مسؤولة إعلانات', 'مسؤول اعلانات', 'مسؤولة اعلانات',
    'للتواصل الإعلاني', 'للتواصل الاعلاني', 'للإعلان والتسويق', 'للاعلان والتسويق',
    'للإعلان على القناة', 'للاعلان على القناة', 'حجز إعلان', 'حجز اعلان',
    'أسعار الإعلانات', 'اسعار الاعلانات', 'تمويل قنوات', 'شراء إعلانات', 'شراء اعلانات',
    'تزويد متابعين', 'رفع مشاهدات', 'تفاعل ومشاهدات', 'وسيط إعلاني', 'وسيط اعلاني',
    'وكالة دعاية', 'وكالة إعلانية', 'وكالة اعلانية', 'تسويق قنوات', 'دعاية وإعلان'
]

# Build SQL regex query from all keywords
SQL_REGEX = '|'.join([re.escape(k) for k in KEYWORDS])

# 1. Fetch from channel_posts
print("[1] Deep scanning `channel_posts` table for all matches...")
cur.execute(f"SELECT channel_username, message_text FROM channel_posts WHERE message_text ~* '{SQL_REGEX}';")
matched_posts = cur.fetchall()
print(f"Found {len(matched_posts)} posts matching advertising keywords.")

# 2. Fetch from leads
print("[2] Deep scanning `leads` table for all matches...")
cur.execute(f"""
    SELECT channel_username, description, contact_username 
    FROM leads 
    WHERE description ~* '{SQL_REGEX}'
       OR contact_username ~* '(ads?|exchange|growth|agency|media|promo|buyer|tbad|tabad|market|traffic)';
""")
matched_leads = cur.fetchall()
print(f"Found {len(matched_leads)} leads matching advertising keywords/handles.")

# 3. Fetch from seen_channels
print("[3] Deep scanning `seen_channels` table...")
try:
    cur.execute(f"SELECT username, title FROM seen_channels WHERE username ~* '(ads?|exchange|growth|agency|media|promo|buyer|tbad|tabad)' OR title ~* '{SQL_REGEX}';")
    matched_seen = cur.fetchall()
    print(f"Found {len(matched_seen)} seen_channels matching.")
except Exception:
    conn.rollback()
    matched_seen = []

USERNAME_REGEX = re.compile(r'(?:@|https?://t\.me/|t\.me/)([a-zA-Z0-9_]{4,32})', re.IGNORECASE)

master_advertisers = {}

def register_lead(username, display_name="", category="", channel="", context="", confidence=10):
    if not username:
        return
    u = username.lower().lstrip('@')
    # Filter generic non-user terms
    if u in ('joinchat', 'addlist', 'everyone', 'share', 'contact', 'admin', 'telegram', 'channel', 'support', 'help', 'bot', 'post', 'public', 'private', 'views', 'followers', 'engagement'):
        return
    if u.endswith('bot') and not any(k in u for k in ['tbad', 'ad', 'exchange', 'promo', 'growth']):
        return
        
    if u not in master_advertisers:
        master_advertisers[u] = {
            'username': f"@{u}",
            'display_name': display_name.strip() if display_name else "",
            'categories': set(),
            'channels': set(),
            'contexts': [],
            'score': 0
        }
        
    if display_name and not master_advertisers[u]['display_name']:
        master_advertisers[u]['display_name'] = display_name.strip()
    if category:
        master_advertisers[u]['categories'].add(category)
    if channel:
        master_advertisers[u]['channels'].add(f"@{channel.lstrip('@')}")
    if context and len(master_advertisers[u]['contexts']) < 3:
        clean = re.sub(r'\s+', ' ', context).strip()
        master_advertisers[u]['contexts'].append(clean[:150])
    master_advertisers[u]['score'] += confidence

# Process Posts
for p in matched_posts:
    text = p['message_text'] or ''
    ch = p['channel_username'] or ''
    
    # Check for direct contact patterns
    for line in text.split('\n'):
        line_kws = [k for k in KEYWORDS if k in line.lower()]
        if line_kws:
            mentions = USERNAME_REGEX.findall(line)
            for m in mentions:
                cat = "مدير تبادل إعلاني" if any('تبادل' in k for k in line_kws) else "وكالة إعلانات ونمو وترافيك"
                register_lead(m, category=cat, channel=ch, context=line, confidence=30)
                
    # Also check all mentions in post if post is heavily focused on growth/ads
    if any(k in text.lower() for k in ['free ad exchange', 'ad agency', 'media buyer', 'growth agency', 'للتبادل الإعلاني', 'للتواصل الإعلاني']):
        for m in USERNAME_REGEX.findall(text):
            register_lead(m, category="وسيط إعلاني / نمو قنوات", channel=ch, context=text, confidence=20)

# Process Leads
for l in matched_leads:
    desc = l['description'] or ''
    cu = l['contact_username'] or ''
    ch = l['channel_username'] or ''
    
    if cu:
        register_lead(cu, category="مسؤول إعلانات القناة الرسمية", channel=ch, context=desc, confidence=25)
        
    for m in USERNAME_REGEX.findall(desc):
        if any(k in m.lower() for k in ['ad', 'exchange', 'growth', 'promo', 'agency', 'media', 'buyer', 'tbad']):
            register_lead(m, category="مسؤول تبادل / وكالة إعلانية", channel=ch, context=desc, confidence=25)

# Process Seen Channels
for s in matched_seen:
    u = s['username']
    t = s.get('title') or ''
    register_lead(u, display_name=t, category="قناة / شبكة إعلانات ونمو", channel=u, context=t, confidence=20)

# Smart Display Name Generator for remaining
for u, data in master_advertisers.items():
    if not data['display_name']:
        clean = u
        if 'ads' in clean:
            name = re.sub(r'ads?', '', clean, flags=re.I).strip('_')
            data['display_name'] = f"{name.capitalize()} Ads" if name else "Ads Agency"
        elif 'exchange' in clean:
            name = re.sub(r'exchange', '', clean, flags=re.I).strip('_')
            data['display_name'] = f"{name.capitalize()} Exchange" if name else "Ad Exchange Hub"
        elif 'growth' in clean:
            name = re.sub(r'growth', '', clean, flags=re.I).strip('_')
            data['display_name'] = f"{name.capitalize()} Growth" if name else "Growth Agency"
        elif 'promo' in clean:
            name = re.sub(r'promo', '', clean, flags=re.I).strip('_')
            data['display_name'] = f"{name.capitalize()} Promo" if name else "Promotion Services"
        elif 'media' in clean:
            name = re.sub(r'media', '', clean, flags=re.I).strip('_')
            data['display_name'] = f"{name.capitalize()} Media" if name else "Media Agency"
        else:
            data['display_name'] = f"مسؤول تبادل / {clean}"

# Filter only strong advertiser profiles
valid_advertisers = [
    d for d in master_advertisers.values()
    if d['score'] >= 20 or any(k in d['username'].lower() for k in ['ad', 'exchange', 'growth', 'agency', 'promo', 'media', 'buyer', 'tbad'])
]

valid_advertisers.sort(key=lambda x: (x['score'], len(x['channels'])), reverse=True)

print(f"\n[+] Total Unique Advertisers, Media Buyers & Growth Agencies Extracted: {len(valid_advertisers)}")

out_data = []
for a in valid_advertisers:
    out_data.append({
        'username': a['username'],
        'display_name': a['display_name'],
        'categories': list(a['categories']),
        'score': a['score'],
        'channels': list(a['channels'])[:5],
        'sample_context': a['contexts'][0] if a['contexts'] else ""
    })

with open('/app/master_advertisers_ultra.json', 'w', encoding='utf-8') as f:
    json.dump(out_data, f, ensure_ascii=False, indent=2)

print("Saved ultra list to /app/master_advertisers_ultra.json")
