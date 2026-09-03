import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('advertisers_mined.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Filter junk
clean_data = []
for d in data:
    u = d['username'].lower()
    if u in ('@tg', '@telegram', '@bot', '@channel', '@admin', '@support', '@user', '@help'):
        continue
    clean_data.append(d)

print(f"Total Profiles Extracted: {len(clean_data)}")

# Group 1: Explicitly Named Managers (فريدة, دينا, فاتن, هاجر, مختار, مايسة, etc.)
named_group = [x for x in clean_data if x['names']]

# Group 2: Dedicated Ad / Exchange / Marketing Handles
ad_handles_group = [
    x for x in clean_data
    if not x['names'] and (
        any(k in x['username'].lower() for k in ['ad', 'tbad', 'mark', 'prom', 'spon', 'media', 'vip', 'pub'])
        or any('تبادل' in r or 'إعلان' in r or 'اعلان' in r for r in x['roles'])
    )
]

# Group 3: General Channel Admin Contacts / Sponsoring Contacts
general_admins = [x for x in clean_data if x not in named_group and x not in ad_handles_group]

print(f"Group 1 (Named Managers): {len(named_group)}")
print(f"Group 2 (Dedicated Ad/Exchange Handles): {len(ad_handles_group)}")
print(f"Group 3 (Channel Sponsoring Admins): {len(general_admins)}")

print("\n" + "="*80)
print("GROUP 1: EXPLICITLY NAMED MANAGERS & ADVERTISERS")
print("="*80)
for i, x in enumerate(named_group, 1):
    names = ", ".join(x['names'])
    channels = ", ".join(x['channels']) if x['channels'] else "قنوات متعددة"
    snip = x['sample_snippet'].replace('\n', ' ')[:100]
    print(f"{i}. {x['username']} | الاسم: {names} | القنوات: {channels}")
    print(f"   البيان: {snip}...")
    print("-" * 60)

print("\n" + "="*80)
print("GROUP 2: DEDICATED AD EXCHANGE & MARKETING SPECIALISTS")
print("="*80)
for i, x in enumerate(ad_handles_group[:30], 1):
    roles = ", ".join(x['roles']) if x['roles'] else "تبادل إعلاني"
    channels = ", ".join(x['channels']) if x['channels'] else "-"
    snip = x['sample_snippet'].replace('\n', ' ')[:100]
    print(f"{i}. {x['username']} | التخصص: {roles} | القنوات: {channels}")
    print(f"   البيان: {snip}...")
    print("-" * 60)
