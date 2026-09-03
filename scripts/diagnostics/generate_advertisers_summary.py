import json

with open('advertisers_mined.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Filter
clean_data = [d for d in data if d['username'].lower() not in ('@tg', '@telegram', '@bot', '@channel', '@admin', '@support', '@user', '@help')]

named_group = [x for x in clean_data if x['names']]
ad_handles = [
    x for x in clean_data
    if not x['names'] and (
        any(k in x['username'].lower() for k in ['ad', 'tbad', 'mark', 'prom', 'spon', 'media', 'vip', 'pub'])
        or any('تبادل' in r or 'إعلان' in r or 'اعلان' in r for r in x['roles'])
    )
]
general_admins = [x for x in clean_data if x not in named_group and x not in ad_handles]

lines = []
lines.append("=" * 80)
lines.append(f"تقرير مسؤولي التبادل الإعلاني والمعلنين المستخرجين من القنوات (الإجمالي: {len(clean_data)})")
lines.append("=" * 80 + "\n")

lines.append("📌 أولاً: مسؤولو ومديرات التبادل الإعلاني بالأسماء الصريحة (دينا، فريدة، فاتن، هاجر، مختار، مايسة، إلخ):")
lines.append("-" * 80)
for i, x in enumerate(named_group, 1):
    names = ", ".join(x['names'])
    channels = ", ".join(x['channels']) if x['channels'] else "قنوات متعددة"
    snip = x['sample_snippet'].replace('\n', ' ')[:120]
    lines.append(f"{i}. {x['username']} | الاسم المستخرج: {names} | القنوات: {channels}")
    lines.append(f"   البيان/النص: {snip}...")
    lines.append("")

lines.append("\n📌 ثانياً: الحسابات المخصصة حصرياً للتبادل الإعلاني والتسويق (Ad Exchange Specialists):")
lines.append("-" * 80)
for i, x in enumerate(ad_handles[:35], 1):
    roles = ", ".join(x['roles']) if x['roles'] else "تبادل إعلاني"
    channels = ", ".join(x['channels']) if x['channels'] else "-"
    snip = x['sample_snippet'].replace('\n', ' ')[:120]
    lines.append(f"{i}. {x['username']} | التخصص: {roles} | القنوات: {channels}")
    lines.append(f"   البيان/النص: {snip}...")
    lines.append("")

lines.append("\n📌 ثالثاً: جهات التواصل الإعلانية وإدارة القنوات (Sponsoring & Channel Admins):")
lines.append("-" * 80)
for i, x in enumerate(general_admins[:25], 1):
    channels = ", ".join(x['channels']) if x['channels'] else "-"
    snip = x['sample_snippet'].replace('\n', ' ')[:120]
    lines.append(f"{i}. {x['username']} | القنوات: {channels}")
    lines.append(f"   البيان/النص: {snip}...")
    lines.append("")

with open('advertisers_summary.txt', 'w', encoding='utf-8') as f:
    f.write("\n".join(lines))

print(f"Summary written to advertisers_summary.txt with {len(lines)} lines.")
