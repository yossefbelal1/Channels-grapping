import json
import re

with open('pure_advertisers_final.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

lines = []
lines.append("=" * 80)
lines.append(f"قائمة المعلنين المحترفين ومدراء التبادل الإعلاني ووكالات النمو على تيليجرام (الإجمالي: {len(data)})")
lines.append("=" * 80 + "\n")

by_cat = {}
for p in data:
    c = p['category']
    by_cat.setdefault(c, []).append(p)

for cat_name, items in by_cat.items():
    lines.append(f"\n📁 {cat_name} (عدد الحسابات: {len(items)}):")
    lines.append("-" * 80)
    for i, it in enumerate(items, 1):
        ch = ", ".join(it['channels']) if it['channels'] else "شبكة قنوات متعددة"
        sn = it['sample_snippet'].replace('\n', ' ')[:120] if it['sample_snippet'] else ""
        lines.append(f"{i:2d}. {it['username']:<25} | القنوات المرتبطة: {ch}")
        if sn:
            lines.append(f"    نص المنشور/البيان: {sn}...")
        lines.append("")

with open('pure_advertisers_report.txt', 'w', encoding='utf-8') as f:
    f.write("\n".join(lines))

print("Wrote report to pure_advertisers_report.txt")
