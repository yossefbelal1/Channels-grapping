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
print("COMPREHENSIVE TELEGRAM ADVERTISER MINING WITH DISPLAY NAMES & KEYWORDS")
print("=" * 80)

# Keywords indicating advertising, exchange, growth, promotion, media buying
EXPANDED_AD_KEYWORDS = [
    'free ad exchange', 'ad exchange', 'promotion & growth', 'promotion and growth',
    'followers', 'views', 'engagement', 'media buyer', 'media buying', 'growth agency',
    'تبادل إعلاني', 'تبادل اعلاني', 'تبادل نشر', 'تبادل قنوات', 'نشر وتبادل',
    'مدير إعلانات', 'مديرة إعلانات', 'مدير اعلانات', 'مديرة اعلانات',
    'مسؤول إعلانات', 'مسؤولة إعلانات', 'مسؤول اعلانات', 'مسؤولة اعلانات',
    'للتواصل الإعلاني', 'للتواصل الاعلاني', 'للإعلان', 'للاعلان', 'للإعلانات', 'للاعلانات',
    'تمويل قنوات', 'شراء إعلانات', 'شراء اعلانات', 'تزويد متابعين', 'رفع مشاهدات',
    'حجز إعلانات', 'حجز اعلانات', 'رعاية قنوات', 'سبونسر'
]

# Regex to detect any username with 'ads' or exchange/growth/promo substrings embedded anywhere
EMBEDDED_AD_HANDLE_REGEX = re.compile(
    r'[a-zA-Z0-9_]*(?:ads|exchange|growth|promo|traffic|sponsor|agency|media|tabad|tbad|buyer|adv)[a-zA-Z0-9_]*',
    re.IGNORECASE
)

USERNAME_FIND_REGEX = re.compile(r'(?:@|https?://t\.me/|t\.me/)([a-zA-Z0-9_]{4,32})', re.IGNORECASE)

# Extract display name pattern near contact lines like:
# "Dina Ads @Dina_ads" or "Azza Ads: @Adsazza" or "Farida (تبادل) @farida_ads"
NAME_WITH_CONTACT_PATTERNS = [
    re.compile(r'([A-Za-z\u0621-\u064A\s]{2,25})\s*(?:[:\-—|»>]+|\s)\s*(?:@|https?://t\.me/|t\.me/)([a-zA-Z0-9_]{4,32})', re.IGNORECASE),
    re.compile(r'(?:@|https?://t\.me/|t\.me/)([a-zA-Z0-9_]{4,32})\s*(?:[:\-—|«<]+|\s)\s*([A-Za-z\u0621-\u064A\s]{2,25})', re.IGNORECASE)
]

mined_results = {}

def add_mined_advertiser(handle, display_name="", source_channel="", matched_kw="", snippet="", confidence=10):
    if not handle:
        return
    h = handle.lower().lstrip('@')
    
    # Filter non-user system keywords
    if h in ('joinchat', 'addlist', 'everyone', 'share', 'contact', 'admin', 'telegram', 'channel', 'support', 'help', 'bot', 'post', 'public', 'private', 'channel_bot', 'view', 'views', 'followers', 'ads', 'exchange'):
        return
        
    # Check if username contains embedded ad keywords
    has_ad_sub = bool(re.search(r'(?:ads|exchange|growth|promo|traffic|agency|media|tabad|tbad|buyer|adv)', h, re.I))
    
    if h not in mined_results:
        mined_results[h] = {
            'username': f"@{h}",
            'display_name': display_name.strip() if display_name else "",
            'has_ad_in_handle': has_ad_sub,
            'matched_keywords': set(),
            'channels': set(),
            'snippets': [],
            'confidence': 0
        }
        
    if display_name and (not mined_results[h]['display_name'] or len(display_name) > len(mined_results[h]['display_name'])):
        mined_results[h]['display_name'] = display_name.strip()
        
    if matched_kw:
        mined_results[h]['matched_keywords'].add(matched_kw)
        
    if source_channel:
        mined_results[h]['channels'].add(f"@{source_channel.lstrip('@')}")
        
    mined_results[h]['confidence'] += confidence
    
    if snippet and len(mined_results[h]['snippets']) < 2:
        clean_snip = re.sub(r'\s+', ' ', snippet).strip()
        mined_results[h]['snippets'].append(clean_snip[:150])

# =========================================================================
# 1. SCAN POSTS (72,232 posts)
# =========================================================================
print("[1] Scanning 72,232 posts in `channel_posts`...")
cur.execute("SELECT channel_username, message_text FROM channel_posts WHERE message_text IS NOT NULL;")
posts = cur.fetchall()

for row in posts:
    ch = row['channel_username'] or ''
    text = row['message_text'] or ''
    text_lower = text.lower()
    
    # Check for keyword matches
    found_kws = [kw for kw in EXPANDED_AD_KEYWORDS if kw in text_lower]
    
    # If text has ad keywords or embedded ad handles
    for kw in found_kws:
        # Find all mentions in the post
        mentions = USERNAME_FIND_REGEX.findall(text)
        for m in mentions:
            # Check for nearby display name
            d_name = ""
            for pat in NAME_WITH_CONTACT_PATTERNS:
                for match in pat.findall(text):
                    if match[0].lower().lstrip('@') == m.lower().lstrip('@'):
                        d_name = match[1].strip()
                    elif match[1].lower().lstrip('@') == m.lower().lstrip('@'):
                        d_name = match[0].strip()
            add_mined_advertiser(m, display_name=d_name, source_channel=ch, matched_kw=kw, snippet=text, confidence=25)
            
    # Also find any embedded ad handles anywhere in post even without explicit keywords
    for m in USERNAME_FIND_REGEX.findall(text):
        if re.search(r'(?:ads|exchange|growth|promo|agency|tabad|tbad)', m, re.I):
            add_mined_advertiser(m, source_channel=ch, matched_kw="Embedded Ad Handle in Post", snippet=text, confidence=20)

# =========================================================================
# 2. SCAN LEADS (8,334 channels)
# =========================================================================
print("[2] Scanning 8,334 channels in `leads`...")
cur.execute("SELECT channel_username, description, contact_username FROM leads;")
leads = cur.fetchall()

for row in leads:
    ch = row['channel_username'] or ''
    desc = row.get('description') or ''
    cu = row.get('contact_username') or ''
    title = ''
    
    # Contact username check
    if cu:
        cu_clean = cu.lstrip('@')
        if re.search(r'(?:ads|exchange|growth|promo|agency|tabad|tbad|media|buyer|adv)', cu_clean, re.I):
            add_mined_advertiser(cu_clean, display_name=title, source_channel=ch, matched_kw="Lead Contact Ad Handle", snippet=desc, confidence=30)
            
    # Description scan
    desc_lower = desc.lower()
    found_kws = [kw for kw in EXPANDED_AD_KEYWORDS if kw in desc_lower]
    for kw in found_kws:
        mentions = USERNAME_FIND_REGEX.findall(desc)
        for m in mentions:
            add_mined_advertiser(m, display_name=title, source_channel=ch, matched_kw=kw, snippet=desc, confidence=25)
            
    for m in USERNAME_FIND_REGEX.findall(desc):
        if re.search(r'(?:ads|exchange|growth|promo|agency|tabad|tbad)', m, re.I):
            add_mined_advertiser(m, display_name=title, source_channel=ch, matched_kw="Embedded Ad Handle in Bio", snippet=desc, confidence=20)

# =========================================================================
# 3. CLEAN UP & ASSIGN INTELLIGENT DISPLAY NAMES
# =========================================================================
# If display_name is empty, generate from username (e.g. @Adsazza -> Azza Ads, @farida_ads -> Farida Ads)
for h, data in mined_results.items():
    if not data['display_name']:
        # Extract name part from handle
        clean = h
        if 'ads' in clean.lower():
            name_part = re.sub(r'ads?', '', clean, flags=re.I).strip('_')
            data['display_name'] = f"{name_part.capitalize()} Ads" if name_part else "Ads Manager"
        elif 'exchange' in clean.lower():
            name_part = re.sub(r'exchange', '', clean, flags=re.I).strip('_')
            data['display_name'] = f"{name_part.capitalize()} Exchange" if name_part else "Ad Exchange"
        elif 'growth' in clean.lower():
            name_part = re.sub(r'growth', '', clean, flags=re.I).strip('_')
            data['display_name'] = f"{name_part.capitalize()} Growth" if name_part else "Growth Agency"
        elif 'promo' in clean.lower():
            name_part = re.sub(r'promo', '', clean, flags=re.I).strip('_')
            data['display_name'] = f"{name_part.capitalize()} Promo" if name_part else "Promotion Manager"
        else:
            data['display_name'] = f"مسؤول تبادل / {clean}"

# Filter: Must have either embedded ad handle OR high confidence with explicit keywords
final_list = [
    d for d in mined_results.values()
    if (d['has_ad_in_handle'] or d['confidence'] >= 25)
    and not any(bad in d['username'].lower() for bad in ['crypto', 'bitcoin', 'binance', 'signal', 'forex_vip', 'botbot'])
]

final_list.sort(key=lambda x: (x['has_ad_in_handle'], x['confidence'], len(x['channels'])), reverse=True)

print(f"\n[+] Total Verified Advertisers / Exchanges Found: {len(final_list)}")

# Format JSON output
output = []
for a in final_list:
    output.append({
        'username': a['username'],
        'display_name': a['display_name'],
        'has_ad_in_handle': a['has_ad_in_handle'],
        'confidence': a['confidence'],
        'channels': list(a['channels'])[:5],
        'keywords': list(a['matched_keywords'])[:4],
        'sample_snippet': a['snippets'][0] if a['snippets'] else ""
    })

with open('/app/deep_advertisers_with_names.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("Saved detailed list to /app/deep_advertisers_with_names.json\n")

print("=" * 80)
print(f"TOP ADVERTISERS & EXCHANGES WITH DISPLAY NAMES (Total: {len(output)}):")
print("=" * 80)
for i, item in enumerate(output[:60], 1):
    ch_str = ", ".join(item['channels']) if item['channels'] else "-"
    kw_str = ", ".join(item['keywords']) if item['keywords'] else "Ad / Exchange"
    snip = item['sample_snippet'][:110] if item['sample_snippet'] else ""
    print(f"{i:2d}. {item['username']:<25} | الاسم: {item['display_name']:<22} | Score: {item['confidence']}")
    print(f"    الكلمات: [{kw_str}] | القنوات: {ch_str}")
    if snip:
        print(f"    السياق: {snip}...")
    print("-" * 80)
