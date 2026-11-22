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

print("=== STEP 1: FETCHING CANDIDATES FOR SCIENTIFIC RE-RANKING ===")
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
        l.subscription
    FROM campaign_logs cl
    JOIN leads l ON cl.lead_id = l.id
    WHERE cl.status IN ('pending_review', 'approved')
      AND l.contact_username IS NOT NULL AND l.contact_username != '';
""")
candidates = cur.fetchall()
print(f"Total candidates to score and approve: {len(candidates)}")

VIP_REGEX = re.compile(r'\b(vip|v\.i\.p|خاصة|الخاصة|مدفوعة|مدفوع|اشتراك|اشتراكات|vip\s*room)\b', re.IGNORECASE)
ACCT_MGMT_REGEX = re.compile(r'(إدارة|ادارة)\s*(حسابات|محافظ|المحافظ|الحسابات)|portfolio\s*management|نسخ\s*صفقات|copy\s*trad', re.IGNORECASE)
BOT_EA_REGEX = re.compile(r'\b(bot|ea|expert|روبوت|اكسبيرت|إكسبيرت|مؤشر|مؤشرات|indicator)\b', re.IGNORECASE)
FUNDED_REGEX = re.compile(r'(شركة\s*تمويل|شركات\s*التمويل|funded|prop\s*firm|تقييم|تحدي|تحديات|pass\s*challenge)', re.IGNORECASE)
GOLD_REGEX = re.compile(r'\b(gold|xauusd|ذهب|الذهب|دهب|سيد\s*الذهب|ملك\s*الذهب)\b', re.IGNORECASE)

updated_count = 0
for r in candidates:
    title = str(r['title'] or '')
    desc = str(r['description'] or '')
    full_text = f"{title} {desc}".lower()

    # 1. Monetization Signals
    has_vip = bool(r['vip'] or VIP_REGEX.search(full_text))
    has_acct_mgmt = bool(r['account_management'] or ACCT_MGMT_REGEX.search(full_text))
    has_sub = bool(r['subscription'] or ('اشتراك' in full_text or 'باقة' in full_text))
    has_bot_ea = bool(BOT_EA_REGEX.search(full_text))
    has_funded = bool(FUNDED_REGEX.search(full_text))
    has_gold = bool(GOLD_REGEX.search(full_text))

    monetization_pts = 0
    services = []
    if has_acct_mgmt:
        monetization_pts += 35
        services.append("إدارة حسابات ومحافظ")
    if has_vip:
        monetization_pts += 30
        services.append("قناة VIP وتوصيات خاصة")
    if has_sub:
        monetization_pts += 15
        services.append("اشتراكات مدفوعة")
    if has_bot_ea:
        monetization_pts += 10
        services.append("روبوتات ومؤشرات تداول")
    if has_funded:
        monetization_pts += 10
        services.append("شركات تمويل وتحديات")

    monetization_score = min(40, monetization_pts)

    # 2. Audience Sweet Spot
    members = r['member_count'] or 0
    if 1500 <= members <= 15000:
        size_score = 25
        size_label = "Optimal Boutique (1.5k-15k)"
    elif 15000 < members <= 35000:
        size_score = 20
        size_label = "Growing Medium (15k-35k)"
    elif 500 <= members < 1500:
        size_score = 15
        size_label = "Small Scalper (500-1.5k)"
    elif 35000 < members <= 70000:
        size_score = 12
        size_label = "Large Community"
    elif members > 70000:
        size_score = 5
        size_label = "Mega / Corporate"
    else:
        size_score = 5
        size_label = "Micro (<500)"

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

    total_cos = min(100, max(15, monetization_score + size_score + contact_score + niche_score))

    if (has_acct_mgmt or has_vip) and total_cos >= 70:
        tier = "P0"
        reason = f"Elite VIP / High-Paying Target ({', '.join(services)}) | {size_label} | High Commercial Propensity."
    elif total_cos >= 55 or has_vip or has_acct_mgmt or has_funded:
        tier = "P1"
        reason = f"High-Value Trading Provider ({', '.join(services) if services else 'Active Signals'}) | {size_label}."
    elif total_cos >= 35:
        tier = "P2"
        reason = f"Standard Trading Community ({size_label}) | Qualified for Channel Exchange."
    else:
        tier = "P3"
        reason = "Informational / Unclassified Trading Channel."

    # Update leads table
    cur.execute("""
        UPDATE leads
        SET outreach_priority = %s,
            outreach_priority_score = %s,
            outreach_priority_reason = %s,
            vip = %s,
            account_management = %s,
            subscription = %s,
            commercial_fit_score = GREATEST(commercial_fit_score, %s)
        WHERE id = %s;
    """, (tier, total_cos, reason, has_vip, has_acct_mgmt, has_sub, monetization_pts, r['lead_id']))

    # Update campaign_logs to 'approved' with new priority and score
    cur.execute("""
        UPDATE campaign_logs
        SET status = 'approved',
            priority = %s,
            priority_score = %s,
            priority_reason = %s,
            commercial_fit_score = %s
        WHERE id = %s;
    """, (tier, total_cos, reason, monetization_pts, r['log_id']))
    updated_count += 1

conn.commit()
print(f"=== STEP 2: Successfully evaluated and approved {updated_count} leads! ===")

# STEP 3: Deduplication enforcement post-approval
print("=== STEP 3: ENFORCING DEDUPLICATION POST-APPROVAL ===")
# 3a. Auto-skip any approved lead if contact was already messaged previously
cur.execute("""
    UPDATE campaign_logs cl
    SET status = 'skipped',
        error_message = 'Deduplicated: Contact already messaged previously',
        sent_at = NOW()
    FROM leads l
    WHERE cl.lead_id = l.id
      AND cl.status = 'approved'
      AND l.contact_username IS NOT NULL AND l.contact_username != ''
      AND LOWER(TRIM(LEADING '@' FROM TRIM(l.contact_username))) IN (
          SELECT DISTINCT LOWER(TRIM(LEADING '@' FROM TRIM(l_sent.contact_username)))
          FROM campaign_logs cl_sent
          JOIN leads l_sent ON cl_sent.lead_id = l_sent.id
          WHERE cl_sent.status = 'sent' AND l_sent.contact_username IS NOT NULL AND l_sent.contact_username != ''
      );
""")
skipped_sent = cur.rowcount
print(f"Skipped contacts already sent: {skipped_sent}")

# 3b. Intra-queue deduplication: keep only the single highest score lead per human contact
cur.execute("""
    WITH ranked_approved AS (
        SELECT cl.id,
               LOWER(TRIM(LEADING '@' FROM TRIM(l.contact_username))) as clean_contact,
               ROW_NUMBER() OVER (
                   PARTITION BY LOWER(TRIM(LEADING '@' FROM TRIM(l.contact_username)))
                   ORDER BY 
                       CASE COALESCE(l.outreach_priority, cl.priority, 'P3')
                           WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END,
                       COALESCE(l.outreach_priority_score, cl.priority_score, 0) DESC,
                       cl.id ASC
               ) as rn
        FROM campaign_logs cl
        JOIN leads l ON cl.lead_id = l.id
        WHERE cl.status = 'approved'
          AND l.contact_username IS NOT NULL AND l.contact_username != ''
    )
    UPDATE campaign_logs
    SET status = 'skipped',
        error_message = 'Deduplicated: Multiple channels share same owner in approved queue',
        sent_at = NOW()
    WHERE id IN (SELECT id FROM ranked_approved WHERE rn > 1);
""")
skipped_queue_dupes = cur.rowcount
print(f"Skipped duplicate channels in approved queue: {skipped_queue_dupes}")
conn.commit()

# STEP 4: Final Summary
print("\n=== STEP 4: FINAL APPROVED CAMPAIGN BREAKDOWN ===")
cur.execute("""
    SELECT 
        priority,
        count(id) as count,
        round(avg(priority_score), 1) as avg_score,
        min(priority_score) as min_score,
        max(priority_score) as max_score
    FROM campaign_logs
    WHERE status = 'approved'
    GROUP BY priority
    ORDER BY 
        CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END;
""")
for s in cur.fetchall():
    print(f"  Tier {s['priority']}: {s['count']} approved leads | Avg Score: {s['avg_score']} (Range: {s['min_score']}-{s['max_score']})")

print("\n=== TOP 10 UPCOMING P0 DISPATCH TARGETS ===")
cur.execute("""
    SELECT l.channel_username, l.title, l.contact_username, l.member_count,
           cl.priority, cl.priority_score, cl.priority_reason
    FROM campaign_logs cl
    JOIN leads l ON cl.lead_id = l.id
    WHERE cl.status = 'approved'
    ORDER BY 
        CASE cl.priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END,
        cl.priority_score DESC
    LIMIT 10;
""")
for t in cur.fetchall():
    t_title = (t['title'] or '')[:25]
    print(f"  [{t['priority']} - Score {t['priority_score']}] @{t['channel_username']} ({t_title}) -> @{t['contact_username']} | Members: {t['member_count']}")

cur.close()
conn.close()
