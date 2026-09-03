import json
import re

with open('master_advertisers_ultra.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Total Profiles in Ultra Master List: {len(data)}")

# Categorize into 4 clean, distinct sections:
# 1. Dedicated Ad Agencies & Growth Hubs (e.g. Growth Engine, Ad Pro FX, Elite Traders Ad, Pro Traders Ad, Adsazza, Farida Ads, Faten Exchange, etc.)
# 2. Individual Ad Managers & Media Buyers (Dina Ads, Maryam Ads, Mohamed Ads, Ads Manager, etc.)
# 3. Direct Channel Ad Managers & Promoters (للإعلان على القناة، مسؤول إعلانات، حجز إعلانات)
# 4. Exchange Networks & Traffic Bots (SudButterfly, Tbadol, etc.)

agencies = []
individual_ads = []
channel_ad_managers = []
exchange_networks = []

for item in data:
    u = item['username'].lower()
    d_name = item['display_name']
    ctx = item.get('sample_context', '')
    
    if any(k in u for k in ['agency', 'growth', 'hub', 'protrader', 'elitetrader', 'engine', 'exchange', 'traffic']):
        agencies.append(item)
    elif 'ads' in u or 'adv' in u or 'promo' in u:
        individual_ads.append(item)
    elif 'tbad' in u or 'bot' in u:
        exchange_networks.append(item)
    else:
        channel_ad_managers.append(item)

lines = []
lines.append("=" * 80)
lines.append(f"الدليل الشامل لكافة المعلنين ووكالات النمو ومدراء التبادل على تيليجرام (الإجمالي: {len(data)})")
lines.append("=" * 80 + "\n")

lines.append(f"📁 1. وكالات النمو والترويج وتبادل القنوات الكبرى (Ad & Growth Agencies) - ({len(agencies)} وكالة/شبكة):")
lines.append("-" * 80)
for i, x in enumerate(agencies, 1):
    ch = ", ".join(x['channels']) if x['channels'] else "شبكة قنوات متعددة"
    lines.append(f"{i:2d}. {x['username']:<25} | الاسم التعريفي: {x['display_name']}")
    lines.append(f"    القنوات المرتبطة: {ch}")
    if x['sample_context']:
        lines.append(f"    السياق/النشاط: {x['sample_context'][:110]}...")
    lines.append("")

lines.append(f"\n📁 2. مسؤولو ومدراء الإعلانات بحسابات ADS الصريحة (Dedicated Ads Specialists) - ({len(individual_ads)} حساب):")
lines.append("-" * 80)
for i, x in enumerate(individual_ads, 1):
    ch = ", ".join(x['channels']) if x['channels'] else "شبكة قنوات متعددة"
    lines.append(f"{i:2d}. {x['username']:<25} | الاسم التعريفي: {x['display_name']}")
    lines.append(f"    القنوات المرتبطة: {ch}")
    if x['sample_context']:
        lines.append(f"    السياق/النشاط: {x['sample_context'][:110]}...")
    lines.append("")

lines.append(f"\n📁 3. مسؤولو حجز الإعلانات والرعاية في القنوات (Sponsoring & Channel Ad Managers) - ({len(channel_ad_managers[:40])} حساب):")
lines.append("-" * 80)
for i, x in enumerate(channel_ad_managers[:40], 1):
    ch = ", ".join(x['channels']) if x['channels'] else "قناة تداول"
    lines.append(f"{i:2d}. {x['username']:<25} | الاسم التعريفي: {x['display_name']}")
    lines.append(f"    القنوات المرتبطة: {ch}")
    if x['sample_context']:
        lines.append(f"    السياق/النشاط: {x['sample_context'][:110]}...")
    lines.append("")

with open('master_ultra_report.txt', 'w', encoding='utf-8') as f:
    f.write("\n".join(lines))

print("Generated master_ultra_report.txt successfully.")
