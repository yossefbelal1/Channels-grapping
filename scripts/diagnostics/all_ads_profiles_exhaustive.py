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
print("EXHAUSTIVE MINING: EVERY PROFILE WITH 'ADS' IN USERNAME, NAME OR POSTS")
print("=" * 80)

# 1. Regex to extract ANY mention containing 'ads' (case-insensitive)
# e.g., @hagar_ads, @HagarAds, @maysa_ads, @MaysaAds, @dina_ads, @farida_ads, @Adsazza, @ads_maneg14, etc.
ADS_MENTION_REGEX = re.compile(r'(?:@|https?://t\.me/|t\.me/)([a-zA-Z0-9_]*ads[a-zA-Z0-9_]*)', re.IGNORECASE)

# 2. Regex to extract ANY text phrase matching "[Name] Ads" or "Ads [Name]" in Arabic or English
# e.g. "هاجر ads", "مايسة ads", "دينا ads", "Hagar Ads", "Maysa Ads", "Dina Ads", "Azza Ads"
NAME_ADS_PHRASE_REGEX = re.compile(
    r'([A-Za-z\u0621-\u064A]{2,20})\s+(?:ads?|إعلانات|اعلانات|exchange)|(?:ads?|إعلانات|اعلانات|exchange)\s+([A-Za-z\u0621-\u064A]{2,20})',
    re.IGNORECASE
)

ALL_USERNAME_REGEX = re.compile(r'(?:@|https?://t\.me/|t\.me/)([a-zA-Z0-9_]{4,32})', re.IGNORECASE)

ads_profiles = {}

def record_profile(username, display_name="", source_channel="", source_text="", context_reason=""):
    if not username:
        return
    u = username.lower().lstrip('@')
    
    # Exclude system noise
    if u in ('joinchat', 'addlist', 'everyone', 'share', 'contact', 'admin', 'telegram', 'channel', 'support', 'help', 'bot', 'post', 'public', 'private', 'views', 'followers', 'engagement', 'ads', 'ad'):
        return
        
    if u not in ads_profiles:
        ads_profiles[u] = {
            'username': f"@{u}",
            'display_name': display_name.strip() if display_name else "",
            'channels_seen': set(),
            'reasons': set(),
            'contexts': [],
            'hit_count': 0
        }
        
    ads_profiles[u]['hit_count'] += 1
    if display_name and (not ads_profiles[u]['display_name'] or len(display_name) > len(ads_profiles[u]['display_name'])):
        ads_profiles[u]['display_name'] = display_name.strip()
    if source_channel:
        ads_profiles[u]['channels_seen'].add(f"@{source_channel.lstrip('@')}")
    if context_reason:
        ads_profiles[u]['reasons'].add(context_reason)
    if source_text and len(ads_profiles[u]['contexts']) < 3:
        clean = re.sub(r'\s+', ' ', source_text).strip()
        ads_profiles[u]['contexts'].append(clean[:160])

# =========================================================================
# Query 1: Search posts with 'ads' or marketer names in message_text
# =========================================================================
print("[1] Scanning 72,232 channel posts for 'ads' and female marketer names...")
cur.execute("""
    SELECT channel_username, message_text 
    FROM channel_posts 
    WHERE message_text ~* '(ads|هاجر|مايسة|ميساء|دينا|فريدة|فريدا|فاتن|عزة|سارة|مختار|ياسمين|نور|منة|إسراء|اسراء|هدير|شهد|شروق|تبادل|exchange)';
""")
posts = cur.fetchall()
print(f"Matched {len(posts)} posts. Extracting...")

for p in posts:
    text = p['message_text'] or ''
    ch = p['channel_username'] or ''
    
    # 1. Extract direct handles with 'ads'
    for handle in ADS_MENTION_REGEX.findall(text):
        record_profile(handle, source_channel=ch, source_text=text, context_reason="Handle contains 'ads' in post")
        
    # 2. Extract name + ads phrases and nearby contact
    for line in text.split('\n'):
        if 'ads' in line.lower() or any(w in line for w in ['تبادل', 'إعلانات', 'اعلانات', 'هاجر', 'مايسة', 'ميساء', 'دينا', 'فريدة', 'فاتن', 'عزة']):
            mentions = ALL_USERNAME_REGEX.findall(line)
            # Find name in line
            d_name = ""
            for name in ['هاجر', 'مايسة', 'ميساء', 'دينا', 'فريدة', 'فريدا', 'فاتن', 'عزة', 'سارة', 'مختار', 'ياسمين', 'نور', 'منة', 'إسراء', 'هدير', 'شهد', 'شروق', 'Hagar', 'Maysa', 'Dina', 'Farida', 'Faten', 'Azza', 'Sara']:
                if name.lower() in line.lower():
                    d_name = f"{name} Ads"
                    break
            for m in mentions:
                record_profile(m, display_name=d_name, source_channel=ch, source_text=line, context_reason="Marketer context in line")

# =========================================================================
# Query 2: Search leads table
# =========================================================================
print("[2] Scanning 8,334 channels in `leads`...")
cur.execute("""
    SELECT channel_username, description, contact_username 
    FROM leads 
    WHERE contact_username ~* 'ads'
       OR description ~* '(ads|هاجر|مايسة|ميساء|دينا|فريدة|فاتن|عزة|مختار|تبادل)';
""")
leads = cur.fetchall()
print(f"Matched {len(leads)} leads. Extracting...")

for l in leads:
    desc = l['description'] or ''
    cu = l['contact_username'] or ''
    ch = l['channel_username'] or ''
    
    if cu:
        if 'ads' in cu.lower():
            record_profile(cu, source_channel=ch, source_text=desc, context_reason="Contact username contains 'ads'")
        elif any(w in desc for w in ['هاجر', 'مايسة', 'دينا', 'فريدة', 'فاتن', 'عزة', 'تبادل', 'إعلانات']):
            record_profile(cu, source_channel=ch, source_text=desc, context_reason="Lead bio has marketer name")
            
    for handle in ADS_MENTION_REGEX.findall(desc):
        record_profile(handle, source_channel=ch, source_text=desc, context_reason="Handle contains 'ads' in bio")

# =========================================================================
# Query 3: Search seen_channels
# =========================================================================
print("[3] Scanning `seen_channels` table...")
try:
    cur.execute("SELECT username, title FROM seen_channels WHERE username ~* 'ads' OR title ~* 'ads';")
    seen = cur.fetchall()
    for s in seen:
        record_profile(s['username'], display_name=s.get('title') or "", source_channel=s['username'], context_reason="Seen channel contains 'ads'")
except Exception:
    conn.rollback()

# Generate smart display names for handles that don't have one
for u, data in ads_profiles.items():
    if not data['display_name']:
        clean = u
        if 'ads' in clean.lower():
            name_part = re.sub(r'ads?', '', clean, flags=re.I).strip('_')
            data['display_name'] = f"{name_part.capitalize()} Ads" if name_part else "Ads Manager"
profiles_list = list(ads_profiles.values())
profiles_list.sort(key=lambda x: (x['hit_count'], len(x['channels_seen'])), reverse=True)

print(f"\n[+] Total Ads & Marketer Profiles Extracted: {len(profiles_list)}")

formatted_output = []
for p in profiles_list:
    formatted_output.append({
        'username': p['username'],
        'display_name': p['display_name'],
        'hit_count': p['hit_count'],
        'channels': list(p['channels_seen'])[:5],
        'reasons': list(p['reasons']),
        'sample_context': p['contexts'][0] if p['contexts'] else ""
    })

with open('/app/all_ads_profiles_exhaustive.json', 'w', encoding='utf-8') as f:
    json.dump(formatted_output, f, ensure_ascii=False, indent=2)

print("Saved exhaustive profiles to /app/all_ads_profiles_exhaustive.json")
