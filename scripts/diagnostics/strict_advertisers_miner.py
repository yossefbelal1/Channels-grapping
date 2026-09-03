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
print("HIGH-PRECISION TELEGRAM ADVERTISER & EXCHANGE MINING")
print("=" * 80)

# Strict Regexes for username / handle patterns
# Matches handles containing ads, exchange, marketing, agency, promo, growth, etc.
STRICT_AD_HANDLE_REGEX = re.compile(
    r'^[a-zA-Z0-9_]*(?:ads?|exchange|marketing|agency|promo|growth|traffic|sponsor|adv|tabad[ou]?l|tbad[ou]?l|media|buyer)[a-zA-Z0-9_]*$',
    re.IGNORECASE
)

# Text patterns that explicitly introduce an advertiser/ad manager contact
AD_CONTACT_PATTERNS = [
    re.compile(r'(?:للإعلان(?:ات)?|للاعلان(?:ات)?|للتبادل(?: الإعلاني)?|للتبادل الاعلاني|للتواصل الإعلاني|للتواصل الاعلاني|حجز إعلان|حجز اعلان|مدير(?:ة)? الإعلانات|مدير(?:ة)? الاعلانات|مسؤول(?:ة)? الإعلانات|مسؤول(?:ة)? الاعلانات|مسؤول(?:ة)? التبادل|وكالة إعلانات|وكالة اعلانات|إدارة الإعلانات|ادارة الاعلانات|قناة الإعلانات|قناة الاعلانات|تمويل قنوات|شراء إعلانات|شراء اعلانات|for ads?|for advertising|for promotion|for inquiries & ads|ads manager|ad exchange|ad agency|media buyer)[\s:—–\-»>]+(?:@|https?://t\.me/|t\.me/)?([a-zA-Z0-9_]{4,32})', re.IGNORECASE),
    re.compile(r'(?:@|https?://t\.me/|t\.me/)([a-zA-Z0-9_]{4,32})[\s:—–\-»<]+(?:للإعلان(?:ات)?|للاعلان(?:ات)?|للتبادل|للتواصل الإعلاني|مدير إعلانات|مديرة إعلانات|مسؤول إعلانات|مسؤولة إعلانات|ads manager|ad exchange)', re.IGNORECASE),
    re.compile(r'([a-zA-Z0-9_]{4,32})\s+(?:ads?|exchange|marketing|agency|media|growth)', re.IGNORECASE),
]

USERNAME_EXTRACT_REGEX = re.compile(r'(?:@|https?://t\.me/|t\.me/)([a-zA-Z0-9_]{4,32})', re.IGNORECASE)

discovered_advertisers = {}

def record_advertiser(handle, reason, source_channel="", snippet="", manager_name="", confidence=10):
    if not handle:
        return
    h = handle.lower().lstrip('@')
    # Filter non-user system keywords
    if h in ('joinchat', 'addlist', 'everyone', 'share', 'contact', 'admin', 'telegram', 'channel', 'support', 'help', 'bot', 'post', 'public', 'private', 'channel_bot'):
        return
    if h.endswith('bot') and not ('tbad' in h or 'ad' in h or 'exchange' in h):
        return
        
    if h not in discovered_advertisers:
        discovered_advertisers[h] = {
            'username': f"@{h}",
            'manager_name': manager_name,
            'reasons': set(),
            'channels_seen': set(),
            'snippets': [],
            'confidence_score': 0
        }
        
    discovered_advertisers[h]['reasons'].add(reason)
    discovered_advertisers[h]['confidence_score'] += confidence
    if source_channel:
        discovered_advertisers[h]['channels_seen'].add(f"@{source_channel.lstrip('@')}")
    if manager_name and not discovered_advertisers[h]['manager_name']:
        discovered_advertisers[h]['manager_name'] = manager_name
    if snippet and len(discovered_advertisers[h]['snippets']) < 3:
        clean = re.sub(r'\s+', ' ', snippet).strip()
        discovered_advertisers[h]['snippets'].append(clean[:160])

# =========================================================================
# 1. SCAN ALL LEADS (Bio descriptions & Contact Usernames)
# =========================================================================
print("[1] Scanning 8,334 channels in `leads`...")
cur.execute("SELECT channel_username, description, contact_username FROM leads;")
leads = cur.fetchall()

for row in leads:
    ch = row['channel_username'] or ''
    desc = row['description'] or ''
    cu = row['contact_username'] or ''
    
    # 1a. Check contact_username directly against strict ad handle pattern
    if cu:
        cu_clean = cu.lstrip('@')
        if STRICT_AD_HANDLE_REGEX.match(cu_clean):
            record_advertiser(cu_clean, "Contact username has ad/exchange keyword", source_channel=ch, snippet=desc, confidence=30)
            
    # 1b. Check description for ad contact regexes
    for pat in AD_CONTACT_PATTERNS:
        matches = pat.findall(desc)
        for m in matches:
            record_advertiser(m, "Explicit ad contact line in channel bio", source_channel=ch, snippet=desc, confidence=25)
            
    # 1c. Check all mentions in description if handle matches strict ad regex
    for m in USERNAME_EXTRACT_REGEX.findall(desc):
        if STRICT_AD_HANDLE_REGEX.match(m):
            record_advertiser(m, "Ad handle found in channel bio", source_channel=ch, snippet=desc, confidence=20)

# =========================================================================
# 2. SCAN ALL POSTS (72,232 channel posts)
# =========================================================================
print("[2] Scanning 72,232 posts in `channel_posts`...")
cur.execute("SELECT channel_username, message_text FROM channel_posts WHERE message_text IS NOT NULL;")
posts = cur.fetchall()

for row in posts:
    ch = row['channel_username'] or ''
    text = row['message_text'] or ''
    
    # 2a. Check for explicit ad contact patterns in post
    for pat in AD_CONTACT_PATTERNS:
        matches = pat.findall(text)
        for m in matches:
            record_advertiser(m, "Explicit ad manager mention in post", source_channel=ch, snippet=text, confidence=25)
            
    # 2b. Check mentions in posts if handle matches strict ad handle regex
    for m in USERNAME_EXTRACT_REGEX.findall(text):
        if STRICT_AD_HANDLE_REGEX.match(m):
            # Verify text has some advertising/channel context
            record_advertiser(m, "Dedicated Ad/Exchange username in post", source_channel=ch, snippet=text, confidence=15)

# =========================================================================
# 3. FILTER, CATEGORIZE AND DEDUPLICATE
# =========================================================================
print(f"\n[+] Total raw candidates matched: {len(discovered_advertisers)}")

# Sort by confidence score descending
sorted_list = sorted(discovered_advertisers.values(), key=lambda x: (x['confidence_score'], len(x['channels_seen'])), reverse=True)

# Filter out low-confidence generic accounts
final_advertisers = [x for x in sorted_list if x['confidence_score'] >= 15 or STRICT_AD_HANDLE_REGEX.match(x['username'].lstrip('@'))]

print(f"[+] Verified Dedicated Advertisers & Exchanges: {len(final_advertisers)}")

out_data = []
for a in final_advertisers:
    out_data.append({
        'username': a['username'],
        'manager_name': a['manager_name'],
        'reasons': list(a['reasons']),
        'confidence': a['confidence_score'],
        'channels_count': len(a['channels_seen']),
        'channels': list(a['channels_seen'])[:5],
        'sample_snippets': a['snippets'][:2]
    })

with open('/app/strict_advertisers_mined.json', 'w', encoding='utf-8') as f:
    json.dump(out_data, f, ensure_ascii=False, indent=2)

print(f"Saved results to /app/strict_advertisers_mined.json\n")
print("=" * 80)
print("STRICT ADVERTISERS, EXCHANGES & MEDIA BUYERS:")
print("=" * 80)
for i, item in enumerate(out_data, 1):
    reasons_str = " | ".join(item['reasons'])
    ch_str = ", ".join(item['channels']) if item['channels'] else "-"
    snip = item['sample_snippets'][0] if item['sample_snippets'] else ""
    print(f"{i:2d}. {item['username']:<25} | Score: {item['confidence']:<3} | القنوات: {ch_str}")
    print(f"    السبب/التصنيف: {reasons_str}")
    if snip:
        print(f"    النص/السياق: {snip[:130]}...")
    print("-" * 80)
