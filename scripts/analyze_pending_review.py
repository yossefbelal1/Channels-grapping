import os
import psycopg2
from psycopg2.extras import RealDictCursor

db_host = os.getenv("DB_HOST", os.getenv("POSTGRES_HOST", "postgres"))
db_port = int(os.getenv("DB_PORT", os.getenv("POSTGRES_PORT", 5432)))
db_name = os.getenv("DB_NAME", os.getenv("POSTGRES_DB", "leadhunter_db"))
db_user = os.getenv("DB_USER", os.getenv("POSTGRES_USER", "postgres"))
db_pass = os.getenv("DB_PASSWORD", os.getenv("POSTGRES_PASSWORD", ""))

conn = psycopg2.connect(host=db_host, port=db_port, dbname=db_name, user=db_user, password=db_pass)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=== 1. PENDING_REVIEW LEADS ANALYSIS ===")
cur.execute("""
    SELECT 
        COALESCE(l.outreach_priority, 'None') as lead_priority,
        COALESCE(cl.priority, 'None') as log_priority,
        COUNT(cl.id) as count,
        COUNT(CASE WHEN l.vip = TRUE THEN 1 END) as vip_count,
        COUNT(CASE WHEN l.account_management = TRUE THEN 1 END) as acct_mgmt_count,
        COUNT(CASE WHEN l.subscription = TRUE THEN 1 END) as sub_count,
        COUNT(CASE WHEN l.forex_score >= 50 THEN 1 END) as high_forex_count,
        COUNT(CASE WHEN l.member_count BETWEEN 1000 AND 30000 THEN 1 END) as sweet_spot_count
    FROM campaign_logs cl
    JOIN leads l ON cl.lead_id = l.id
    WHERE cl.status = 'pending_review'
    GROUP BY l.outreach_priority, cl.priority
    ORDER BY count DESC;
""")
for r in cur.fetchall():
    print(dict(r))

print("\n=== 2. CURRENT APPROVED BREAKDOWN ===")
cur.execute("""
    SELECT 
        COALESCE(cl.priority, 'None') as log_priority,
        COUNT(cl.id) as count,
        COUNT(CASE WHEN l.vip = TRUE THEN 1 END) as vip_count,
        COUNT(CASE WHEN l.account_management = TRUE THEN 1 END) as acct_mgmt_count
    FROM campaign_logs cl
    JOIN leads l ON cl.lead_id = l.id
    WHERE cl.status = 'approved'
    GROUP BY cl.priority
    ORDER BY count DESC;
""")
for r in cur.fetchall():
    print(dict(r))

print("\n=== 3. TOP MONETIZATION CANDIDATES IN PENDING_REVIEW ===")
cur.execute("""
    SELECT l.channel_username, l.title, l.contact_username, l.member_count,
           l.forex_score, l.commercial_fit_score, l.vip, l.account_management, l.subscription,
           l.outreach_priority, l.outreach_priority_score, l.description
    FROM campaign_logs cl
    JOIN leads l ON cl.lead_id = l.id
    WHERE cl.status = 'pending_review'
      AND (l.vip = TRUE OR l.account_management = TRUE OR l.subscription = TRUE OR l.commercial_fit_score >= 50)
    ORDER BY l.commercial_fit_score DESC, l.outreach_priority_score DESC
    LIMIT 10;
""")
top_candidates = cur.fetchall()
print(f"Total strong monetization candidates in pending_review: {len(top_candidates)}")
for c in top_candidates:
    print(f"  @{c['channel_username']} ({c['title']}) -> Contact: @{c['contact_username']} | VIP:{c['vip']} | AcctMgmt:{c['account_management']} | Score:{c['outreach_priority_score']} | Fit:{c['commercial_fit_score']}")

cur.close()
conn.close()
