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
print("EXHAUSTIVE MINING: ALL TELEGRAM ADVERTISERS, EXCHANGES & MEDIA BUYERS")
print("=" * 80)

# Step 1: Scan all posts for ANY mention where post contains exchange/ad keywords
cur.execute("""
    SELECT channel_username, message_id, timestamp, message_text 
    FROM channel_posts 
    WHERE message_text ~* '(للتبادل|تبادل|إعلاني|اعلاني|مدير إعلانات|مديرة إعلانات|للتواصل الإعلاني|للاعلانات|للإعلانات|تمويل|دعاية|ترويج|exchange|adpro|farida_ads|fatenexchange|growthengine|ads|marketing)'
    ORDER BY timestamp DESC;
""")
ad_posts = cur.fetchall()
print(f"Found {len(ad_posts)} posts specifically containing ad/exchange/marketing intents.")

# Step 2: Scan all leads descriptions & contacts
cur.execute("""
    SELECT channel_username, contact_username, description 
    FROM leads 
    WHERE description ~* '(للتبادل|تبادل|إعلاني|اعلاني|مدير إعلانات|مديرة إعلانات|للتواصل الإعلاني|للاعلانات|للإعلانات|تمويل|دعاية|ترويج|exchange|ads|marketing)'
       OR contact_username ~* '(ad|exchange|tbad|tabad|mark|growth|prom|media|agency)';
""")
ad_leads = cur.fetchall()
print(f"Found {len(ad_leads)} leads with explicit ad/exchange bios or contacts.")

USERNAME_REGEX = re.compile(r'(?:@|https?://t\.me/|t\.me/)([a-zA-Z0-9_]{4,32})', re.IGNORECASE)

ad_managers = {}

def register_manager(handle, role_tag, channel="", text_snippet="", manager_name=""):
    if not handle:
        return
    h = handle.lower().lstrip('@')
    if h in ('joinchat', 'addlist', 'everyone', 'share', 'contact', 'admin', 'telegram', 'channel', 'support', 'help'):
        return
        
    if h not in ad_managers:
        ad_managers[h] = {
            'username': f"@{h}",
            'manager_name': manager_name or "",
            'role_types': set(),
            'channels': set(),
            'contexts': [],
            'hit_count': 0
        }
    
    ad_managers[h]['hit_count'] += 1
    if role_tag:
        ad_managers[h]['role_types'].add(role_tag)
    if channel:
        ad_managers[h]['channels'].add(f"@{channel.lstrip('@')}")
    if manager_name and not ad_managers[h]['manager_name']:
        ad_managers[h]['manager_name'] = manager_name
    if text_snippet and len(ad_managers[h]['contexts']) < 3:
        clean = re.sub(r'\s+', ' ', text_snippet).strip()
        ad_managers[h]['contexts'].append(clean[:150])

# Process Ad Posts
for p in ad_posts:
    text = p['message_text']
    ch = p['channel_username']
    
    # Check for direct lines with contact info for ads
    for line in text.split('\n'):
        # If line has ad intent
        if any(w in line.lower() for w in ['تبادل', 'إعلان', 'اعلان', 'إعلاني', 'اعلاني', 'تواصل', 'ads', 'exchange', 'marketing', 'agency']):
            mentions = USERNAME_REGEX.findall(line)
            for m in mentions:
                role = "مدير تبادل إعلاني" if 'تبادل' in line else "مسؤول إعلانات / تسويق"
                # Check for explicit manager name
                m_name = ""
                for n in ['دينا', 'فاتن', 'فريدة', 'فريدا', 'هاجر', 'مايسة', 'ميساء', 'مختار', 'سارة', 'نور', 'ياسمين', 'ريم', 'منة']:
                    if n in line:
                        m_name = n
                        break
                register_manager(m, role, channel=ch, text_snippet=line, manager_name=m_name)
                
    # Also catch all mentions in the post if post is specifically an ad broker post
    if any(w in text.lower() for w in ['للتبادل الإعلاني', 'للتبادل الاعلاني', 'للتواصل الإعلاني', 'للتواصل الاعلاني', 'للاعلانات', 'للإعلانات']):
        all_m = USERNAME_REGEX.findall(text)
        for m in all_m:
            register_manager(m, "وسيط / مدير تبادل إعلاني", channel=ch, text_snippet=text)

# Process Ad Leads
for l in ad_leads:
    desc = l.get('description') or ''
    cu = l.get('contact_username')
    ch = l.get('channel_username')
    
    if cu:
        role = "مسؤول إعلانات القناة" if any(w in desc.lower() for w in ['اعلان', 'إعلان', 'تبادل', 'ads']) else "جهة اتصال تجارية"
        register_manager(cu, role, channel=ch, text_snippet=desc)
        
    for line in desc.split('\n'):
        if any(w in line.lower() for w in ['تبادل', 'إعلان', 'اعلان', 'ads', 'exchange', 'تواصل']):
            for m in USERNAME_REGEX.findall(line):
                register_manager(m, "مدير تبادل / إعلانات في البايو", channel=ch, text_snippet=desc)

# Convert to list and sort by hits and channels
managers_list = list(ad_managers.values())
managers_list.sort(key=lambda x: (len(x['channels']), x['hit_count'], len(x['role_types'])), reverse=True)

print(f"\n[+] Total Ad Exchange Managers & Advertisers Extracted: {len(managers_list)}")

# Save full results
out_data = []
for m in managers_list:
    out_data.append({
        'username': m['username'],
        'manager_name': m['manager_name'],
        'roles': list(m['role_types']),
        'channels_count': len(m['channels']),
        'channels': list(m['channels'])[:5],
        'hit_count': m['hit_count'],
        'sample_context': m['contexts'][0] if m['contexts'] else ""
    })

with open('/app/telegram_ad_managers_master.json', 'w', encoding='utf-8') as f:
    json.dump(out_data, f, ensure_ascii=False, indent=2)

print("Saved master list to /app/telegram_ad_managers_master.json\n")
print("=" * 80)
print(f"MASTER LIST: TELEGRAM AD MANAGERS & EXCHANGES (Top 50):")
print("=" * 80)
for i, m in enumerate(out_data[:50], 1):
    name_str = f" ({m['manager_name']})" if m['manager_name'] else ""
    roles_str = ", ".join(m['roles']) if m['roles'] else "تبادل / إعلانات"
    ch_str = ", ".join(m['channels']) if m['channels'] else "-"
    print(f"{i:2d}. {m['username']:<25}{name_str} | {roles_str} | قنوات: {m['channels_count']}")
    if m['sample_context']:
        print(f"    السياق: {m['sample_context'][:120]}...")
    print("-" * 80)
