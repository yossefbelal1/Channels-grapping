import json
import re

with open('all_ads_profiles_exhaustive.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Total Profiles in Exhaustive Dataset: {len(data)}")

# Group 1: Explicitly Named Ads Marketers (Farida Ads, Azza Ads, Hagar Ads, Maysa Ads, Dina Ads, Faten Ads, Sara Ads, etc.)
# Group 2: Usernames containing 'ads' anywhere (e.g. @farida_ads, @Adsazza, @maryamads1, @mohamed_ads97, @ads_maneg14, @elitetradersad, @protradersad, @adprofx, etc.)
# Group 3: Growth & Exchange Agencies and Channels

named_marketers = []
ads_handles = []
other_marketers = []

for item in data:
    u = item['username'].lower()
    d_name = item['display_name']
    ctx = item.get('sample_context', '')
    
    # Check if handle contains 'ads'
    has_ads = 'ads' in u
    
    # Check if there is an explicit female marketer name
    is_named = any(n in d_name.lower() or n in u for n in ['hagar', 'maysa', 'dina', 'farida', 'faten', 'azza', 'sara', 'nour', 'menna', 'esraa', 'hadeer', 'هاجر', 'مايسة', 'ميساء', 'دينا', 'فريدة', 'فاتن', 'عزة', 'سارة', 'مختار', 'ياسمين'])
    
    if is_named:
        named_marketers.append(item)
    elif has_ads:
        ads_handles.append(item)
    else:
        other_marketers.append(item)

print(f"Group 1 (Named Marketers): {len(named_marketers)}")
print(f"Group 2 (Direct 'ads' Handles): {len(ads_handles)}")
print(f"Group 3 (Other Exchange & Promo): {len(other_marketers)}")

# Print detailed view
lines = []
lines.append("=" * 80)
lines.append(f"الدليل النهائي الشامل للمسوقين والمعلنين (مع وجود 'ADS' في اليوزر/الاسم)")
lines.append("=" * 80 + "\n")

lines.append("📌 أولاً: مسؤولو ومديرات الإعلانات بالأسماء الصريحة (Farida, Azza, Hagar, Maysa, Dina, Faten, Sara):")
lines.append("-" * 80)
for i, x in enumerate(named_marketers, 1):
    ch = ", ".join(x['channels']) if x['channels'] else "شبكة تداول"
    lines.append(f"{i:2d}. {x['username']:<24} | الاسم التعريفي: {x['display_name']:<22} | القنوات: {ch}")
    if x['sample_context']:
        lines.append(f"    النص/السياق: {x['sample_context'][:100]}...")
    lines.append("")

lines.append("\n📌 ثانياً: جميع الحسابات والوكالات التي تحتوي على كلمة 'ADS' في اليوزر أو الاسم:")
lines.append("-" * 80)
for i, x in enumerate(ads_handles, 1):
    ch = ", ".join(x['channels']) if x['channels'] else "قنوات ترويج"
    lines.append(f"{i:2d}. {x['username']:<24} | الاسم التعريفي: {x['display_name']:<22} | القنوات: {ch}")
    if x['sample_context']:
        lines.append(f"    النص/السياق: {x['sample_context'][:100]}...")
    lines.append("")

with open('final_exhaustive_ads_report.txt', 'w', encoding='utf-8') as f:
    f.write("\n".join(lines))

print("Saved report to final_exhaustive_ads_report.txt")
