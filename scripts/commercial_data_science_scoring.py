import os
import re
import psycopg2
from psycopg2.extras import RealDictCursor

db_host = os.getenv("DB_HOST", os.getenv("POSTGRES_HOST", "postgres"))
db_port = int(os.getenv("DB_PORT", os.getenv("POSTGRES_PORT", 5432)))
db_name = os.getenv("DB_NAME", os.getenv("POSTGRES_DB", "leadhunter_db"))
db_user = os.getenv("DB_USER", os.getenv("POSTGRES_USER", "postgres"))
db_pass = os.getenv("DB_PASSWORD", os.getenv("POSTGRES_PASSWORD", ""))

conn = psycopg2.connect(host=db_host, port=db_port, dbname=db_name, user=db_user, password=db_pass)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=== DATA SCIENCE COMMERCIAL SCORING SIMULATION ===")

cur.execute("""
    SELECT 
        cl.id as log_id,
        l.id as lead_id,
        l.channel_username,
        l.title,
        l.description,
        l.contact_username,
        l.member_count,
        COALESCE(l.forex_score, 0) as forex_score,
        COALESCE(l.forex_intent_score, 0) as forex_intent_score,
        COALESCE(l.commercial_fit_score, 0) as commercial_fit_score,
        l.vip,
        l.account_management,
        l.subscription,
        cl.status as current_status,
        cl.priority as current_priority
    FROM campaign_logs cl
    JOIN leads l ON cl.lead_id = l.id
    WHERE cl.status IN ('pending_review', 'approved')
      AND l.contact_username IS NOT NULL AND l.contact_username != '';
""")
rows = cur.fetchall()
print(f"Total rows fetched for analysis: {len(rows)}")

VIP_REGEX = re.compile(r'\b(vip|v\.i\.p|خاصة|الخاصة|مدفوعة|مدفوع|اشتراك|اشتراكات|vip\s*room)\b', re.IGNORECASE)
ACCT_MGMT_REGEX = re.compile(r'(إدارة|ادارة)\s*(حسابات|محافظ|المحافظ|الحسابات)|portfolio\s*management|نسخ\s*صفقات|copy\s*trad', re.IGNORECASE)
BOT_EA_REGEX = re.compile(r'\b(bot|ea|expert|روبوت|اكسبيرت|إكسبيرت|مؤشر|مؤشرات|indicator)\b', re.IGNORECASE)
FUNDED_REGEX = re.compile(r'(شركة\s*تمويل|شركات\s*التمويل|funded|prop\s*firm|تقييم|تحدي|تحديات|pass\s*challenge)', re.IGNORECASE)
GOLD_REGEX = re.compile(r'\b(gold|xauusd|ذهب|الذهب|دهب|سيد\s*الذهب|ملك\s*الذهب)\b', re.IGNORECASE)

scored_leads = []

for r in rows:
    title = str(r['title'] or '')
    desc = str(r['description'] or '')
    full_text = f"{title} {desc}".lower()
    
    # 1. Monetization Signals
    has_vip = r['vip'] or bool(VIP_REGEX.search(full_text))
    has_acct_mgmt = r['account_management'] or bool(ACCT_MGMT_REGEX.search(full_text))
    has_sub = r['subscription'] or ('اشتراك' in full_text or 'باقة' in full_text)
    has_bot_ea = bool(BOT_EA_REGEX.search(full_text))
    has_funded = bool(FUNDED_REGEX.search(full_text))
    has_gold = bool(GOLD_REGEX.search(full_text))

    monetization_pts = 0
    services_found = []
    if has_acct_mgmt:
        monetization_pts += 35
        services_found.append("Account Management")
    if has_vip:
        monetization_pts += 30
        services_found.append("VIP Channel")
    if has_sub:
        monetization_pts += 15
        services_found.append("Subscriptions")
    if has_bot_ea:
        monetization_pts += 10
        services_found.append("Trading EAs/Bots")
    if has_funded:
        monetization_pts += 10
        services_found.append("Funded Accounts")
    
    monetization_score = min(40, monetization_pts) # Max 40 pts

    # 2. Audience Sweet Spot
    members = r['member_count'] or 0
    if 1500 <= members <= 15000:
        size_score = 25  # Prime boutique sweet-spot
    elif 15000 < members <= 35000:
        size_score = 20
    elif 500 <= members < 1500:
        size_score = 15
    elif 35000 < members <= 70000:
        size_score = 12
    elif members > 70000:
        size_score = 5   # Impersonal / Corporate
    else:
        size_score = 5   # Very small (<500)

    # 3. Direct Contact Authority
    contact = str(r['contact_username'] or '').lower().lstrip('@')
    if any(k in contact for k in ['owner', 'ceo', 'founder', 'trader', 'captain', 'king', 'master', 'vip']):
        contact_score = 20
    elif any(k in contact for k in ['admin', 'support', 'contact', 'tele']):
        contact_score = 15
    else:
        contact_score = 12

    # 4. Niche Value (Gold/Forex)
    niche_score = 0
    if has_gold:
        niche_score += 10
    if r['forex_score'] >= 50 or any(k in full_text for k in ['forex', 'فوركس', 'تداول', 'توصيات', 'صفقات']):
        niche_score += 5
    niche_score = min(15, niche_score)

    total_cos = monetization_score + size_score + contact_score + niche_score
    total_cos = min(100, max(10, total_cos))

    # Priority Tier
    if (has_acct_mgmt or has_vip) and total_cos >= 70:
        tier = "P0"
        reason = f"Elite VIP / High-Paying Target: Confirmed commercial offerings ({', '.join(services_found)}) with high propensity to partner."
    elif total_cos >= 55 or has_vip or has_acct_mgmt or has_funded:
        tier = "P1"
        reason = f"High-Value Signals & Trading Community: Active monetization ({', '.join(services_found) if services_found else 'Active signals'}) in optimal growth bracket."
    elif total_cos >= 35:
        tier = "P2"
        reason = "Standard Trading Community: Qualified audience with potential interest in channel exchange."
    else:
        tier = "P3"
        reason = "Informational / Unclassified Trading Target."

    scored_leads.append({
        "log_id": r['log_id'],
        "lead_id": r['lead_id'],
        "channel": r['channel_username'],
        "contact": r['contact_username'],
        "members": members,
        "services": services_found,
        "cos_score": total_cos,
        "tier": tier,
        "reason": reason
    })

tier_summary = {}
for s in scored_leads:
    tier_summary[s['tier']] = tier_summary.get(s['tier'], 0) + 1

print("\n=== SIMULATED TIER DISTRIBUTION ===")
for t in ["P0", "P1", "P2", "P3"]:
    print(f"  {t}: {tier_summary.get(t, 0)} leads")

print("\n=== TOP 10 ELITE TARGETS (P0) ===")
p0_leads = [s for s in scored_leads if s['tier'] == "P0"]
p0_leads.sort(key=lambda x: x['cos_score'], reverse=True)
for s in p0_leads[:10]:
    print(f"  @{s['channel']} -> @{s['contact']} | COS: {s['cos_score']} | Members: {s['members']} | Services: {s['services']}")

cur.close()
conn.close()
