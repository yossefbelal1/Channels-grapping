import json
import re

with open('strict_advertisers_mined.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Pure Advertiser keywords in handle
PURE_AD_HANDLE_REGEX = re.compile(
    r'(?:ads?|exchange|marketing|agency|promo|growth|traffic|sponsor|adv|tabad|tbad|buyer)',
    re.I
)

# Words that indicate trading channels, signals, courses or ordinary traders (to filter out)
EXCLUDE_TRADER_WORDS = [
    'signals', 'crypto', 'forex', 'academy', 'trading', 'trader', 'gold', 'scalping',
    'analyst', 'chart', 'market', 'vip', 'invest', 'cash', 'broker', 'news', 'prop',
    'bank', 'pips', 'profit', 'daily', 'bot'
]

pure_ad_list = []

for item in data:
    u = item['username'].lower()
    snips = " ".join(item['sample_snippets']).lower()
    reasons = " ".join(item['reasons']).lower()
    
    # Must have ad keywords in username OR explicit ad contact reason
    has_ad_handle = bool(PURE_AD_HANDLE_REGEX.search(u))
    has_explicit_ad_line = any(k in snips for k in [
        'للإعلان', 'للاعلان', 'للتبادل', 'تبادل اعلاني', 'تبادل إعلاني', 
        'مدير إعلانات', 'مديرة إعلانات', 'مسؤول الإعلانات', 'for ads', 'ad exchange',
        'تواصل إعلاني', 'للتواصل الاعلاني', 'للتواصل الإعلاني', 'نشر وتبادل'
    ])
    
    if not (has_ad_handle or has_explicit_ad_line):
        continue
        
    # Categorize
    cat = "معلن / وسيط إعلانات"
    if 'exchange' in u or 'تبادل' in snips:
        cat = "مدير تبادل إعلاني (Exchange Manager)"
    elif 'growth' in u or 'agency' in u or 'traffic' in u or 'marketing' in u:
        cat = "وكالة تسويق ونمو قنوات (Growth & Agency)"
    elif 'ads' in u or 'adv' in u or 'promo' in u:
        cat = "مسؤول إعلانات وترويج (Ads Specialist)"
    elif 'للإعلان' in snips or 'حجز' in snips:
        cat = "حساب حجز الإعلانات والرعاية"
        
    pure_ad_list.append({
        'username': item['username'],
        'category': cat,
        'channels': item['channels'],
        'sample_snippet': item['sample_snippets'][0] if item['sample_snippets'] else ""
    })

# Deduplicate by username
seen = set()
unique_pure_ads = []
for p in pure_ad_list:
    if p['username'] not in seen:
        seen.add(p['username'])
        unique_pure_ads.append(p)

print(f"Total Pure Advertisers Extracted: {len(unique_pure_ads)}")

# Group by category
by_cat = {}
for p in unique_pure_ads:
    c = p['category']
    by_cat.setdefault(c, []).append(p)

with open('pure_advertisers_final.json', 'w', encoding='utf-8') as f:
    json.dump(unique_pure_ads, f, ensure_ascii=False, indent=2)

for c, items in by_cat.items():
    print(f"\n{'='*70}\n{c} ({len(items)} حساب):\n{'='*70}")
    for i, it in enumerate(items[:20], 1):
        ch = ", ".join(it['channels']) if it['channels'] else "-"
        sn = it['sample_snippet'].replace('\n', ' ')[:90]
        print(f"{i:2d}. {it['username']:<25} | القنوات: {ch}")
        if sn:
            print(f"    السياق: {sn}...")
