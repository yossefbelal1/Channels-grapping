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

print("=" * 80)
print("DEEP MINING: PROFESSIONAL ADVERTISERS, AD MANAGERS & EXCHANGES ON TELEGRAM")
print("=" * 80)

# Keywords indicating dedicated advertiser / exchange / marketer roles
AD_ROLE_KEYWORDS = [
    'تبادل', 'إعلاني', 'اعلاني', 'تبادل إعلاني', 'تبادل اعلاني',
    'مدير إعلانات', 'مديرة إعلانات', 'مدير اعلانات', 'مديرة اعلانات',
    'مسؤول إعلانات', 'مسؤولة إعلانات', 'مسؤول اعلانات', 'مسؤولة اعلانات',
    'للتواصل الإعلاني', 'للتواصل الاعلاني', 'للإعلان', 'للاعلان', 'للإعلانات', 'للاعلانات',
    'تبادل نشر', 'تبادل قنوات', 'نشر وتبادل', 'تمويل قنوات', 'رعاية', 'سبونسر',
    'agency', 'ads', 'marketing', 'exchange', 'growth', 'promo', 'media'
]

# Patterns for usernames of advertisers
AD_USERNAME_PATTERNS = [
    re.compile(r'ads?', re.I),
    re.compile(r'exchange', re.I),
    re.compile(r'tbad', re.I),
    re.compile(r'tabad', re.I),
    re.compile(r'market', re.I),
    re.compile(r'growth', re.I),
    re.compile(r'promo', re.I),
    re.compile(r'media', re.I),
    re.compile(r'agency', re.I),
    re.compile(r'sponsor', re.I),
    re.compile(r'adv', re.I),
    re.compile(r'dina', re.I),
    re.compile(r'farida', re.I),
    re.compile(r'faten', re.I),
    re.compile(r'hagar', re.I),
    re.compile(r'maysa', re.I),
    re.compile(r'mokhtar', re.I)
]

USERNAME_EXTRACT_REGEX = re.compile(r'(?:@|https?://t\.me/|t\.me/)([a-zA-Z0-9_]{4,32})', re.IGNORECASE)

advertisers_map = {}

def process_text_for_advertisers(text, source_channel="", source_type="post"):
    if not text:
        return
    
    # 1. Search for explicit contact patterns around ad keywords
    lines = text.split('\n')
    for line in lines:
        has_ad_signal = any(k in line.lower() for k in AD_ROLE_KEYWORDS)
        
        # Find all mentions in this line or surrounding text
        mentions = USERNAME_EXTRACT_REGEX.findall(line)
        if not mentions and has_ad_signal:
            # check whole text mentions if the line had the ad keyword
            mentions = USERNAME_EXTRACT_REGEX.findall(text)
            
        for m in mentions:
            m_clean = m.lower().lstrip('@')
            if m_clean in ('joinchat', 'addlist', 'everyone', 'share', 'contact', 'admin', 'bot', 'telegram'):
                continue
            if m_clean.endswith('bot'):
                # Note bot exchange bots separately if useful, or include as exchange bot
                pass
                
            is_ad_username = any(p.search(m_clean) for p in AD_USERNAME_PATTERNS)
            
            if has_ad_signal or is_ad_username:
                if m_clean not in advertisers_map:
                    advertisers_map[m_clean] = {
                        'username': f"@{m_clean}",
                        'is_ad_handle': is_ad_username,
                        'ad_signals_count': 0,
                        'channels_seen': set(),
                        'snippets': [],
                        'matched_keywords': set(),
                        'names_found': set()
                    }
                    
                advertisers_map[m_clean]['ad_signals_count'] += 1
                if source_channel:
                    advertisers_map[m_clean]['channels_seen'].add(f"@{source_channel.lstrip('@')}")
                
                # Check for names
                for name in ['دينا', 'dina', 'فاتن', 'faten', 'هاجر', 'hagar', 'مايسة', 'ميساء', 'maysa', 'فريدا', 'فريدة', 'farida', 'مختار', 'mokhtar', 'سارة', 'sara', 'نور', 'nour']:
                    if name in text.lower() or name in m_clean:
                        advertisers_map[m_clean]['names_found'].add(name.capitalize())
                        
                for kw in AD_ROLE_KEYWORDS:
                    if kw in text.lower():
                        advertisers_map[m_clean]['matched_keywords'].add(kw)
                        
                if len(advertisers_map[m_clean]['snippets']) < 3 and len(line.strip()) > 10:
                    clean_line = re.sub(r'\s+', ' ', line).strip()
                    advertisers_map[m_clean]['snippets'].append(clean_line[:160])

# 1. Scan all posts
print("[1] Deep scanning 72,232 posts in `channel_posts`...")
cur.execute("SELECT channel_username, message_text FROM channel_posts WHERE message_text IS NOT NULL;")
all_posts = cur.fetchall()
print(f"Loaded {len(all_posts)} posts from DB. Processing...")
for p in all_posts:
    process_text_for_advertisers(p['message_text'], source_channel=p['channel_username'], source_type="post")

# 2. Scan all leads
print("\n[2] Deep scanning 8,334 channels in `leads`...")
cur.execute("SELECT channel_username, description, contact_username FROM leads WHERE description IS NOT NULL OR contact_username IS NOT NULL;")
all_leads = cur.fetchall()
print(f"Loaded {len(all_leads)} leads from DB. Processing...")
for l in all_leads:
    combined_text = f"{l.get('description') or ''}\n{l.get('contact_username') or ''}"
    process_text_for_advertisers(combined_text, source_channel=l['channel_username'], source_type="lead")

print(f"\n[+] Raw extracted candidates: {len(advertisers_map)}")

# Filter and Score candidates
# Prioritize:
# 1. Dedicated Ad handles (e.g. @adprofx, @farida_ads, @fatenexchange, etc.)
# 2. Strong ad signals (matched keywords >= 2 or channels_seen >= 2)
qualified_advertisers = []
for k, data in advertisers_map.items():
    score = 0
    if data['is_ad_handle']:
        score += 5
    if len(data['channels_seen']) > 1:
        score += len(data['channels_seen']) * 2
    if data['ad_signals_count'] > 1:
        score += data['ad_signals_count']
    if any(k in data['matched_keywords'] for k in ['تبادل', 'إعلاني', 'مدير إعلانات', 'للتواصل الإعلاني', 'exchange', 'ads', 'agency', 'growth']):
        score += 3
        
    data['score'] = score
    # Must have either ad handle pattern OR explicit ad keyword
    if data['is_ad_handle'] or any(k in data['matched_keywords'] for k in ['تبادل', 'إعلاني', 'مدير إعلانات', 'للتواصل الإعلاني', 'exchange', 'ads', 'agency', 'growth', 'promo']):
        qualified_advertisers.append(data)

# Sort by score descending
qualified_advertisers.sort(key=lambda x: x['score'], reverse=True)

print(f"[+] Highly Qualified Advertisers & Ad Exchanges Found: {len(qualified_advertisers)}")

# Format JSON output
output = []
for a in qualified_advertisers:
    output.append({
        'username': a['username'],
        'score': a['score'],
        'names': list(a['names_found']),
        'signals_count': a['ad_signals_count'],
        'channels_count': len(a['channels_seen']),
        'channels': list(a['channels_seen'])[:6],
        'keywords': list(a['matched_keywords'])[:5],
        'sample_snippets': a['snippets'][:2]
    })

out_file = "/app/advertisers_deep_mined.json"
with open(out_file, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"Saved results to {out_file}\n")
print("=" * 80)
print(f"TOP ADVERTISERS, EXCHANGES & GROWTH AGENCIES (Total: {len(output)}):")
print("=" * 80)
for i, item in enumerate(output[:60], 1):
    names_str = f" | الاسم: {', '.join(item['names'])}" if item['names'] else ""
    keywords_str = ", ".join(item['keywords']) if item['keywords'] else "تبادل / إعلانات"
    ch_str = ", ".join(item['channels']) if item['channels'] else "-"
    snip = item['sample_snippets'][0] if item['sample_snippets'] else ""
    print(f"{i:2d}. {item['username']:<25}{names_str} | إشارات: {item['signals_count']} | قنوات: {item['channels_count']}")
    print(f"    الكلمات: [{keywords_str}] | القنوات: {ch_str}")
    if snip:
        print(f"    النص: {snip[:120]}...")
    print("-" * 80)
