import subprocess

REMOTE_KEY = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"
REMOTE_HOST = "167.233.246.102"

sql = """
SELECT 
    COUNT(*) as total_new_leads,
    COUNT(*) FILTER (WHERE lead_score >= 10 OR tier IS NOT NULL) as old_qualified_count,
    COUNT(*) FILTER (
        WHERE status = 'new'
          AND COALESCE(forex_intent_score, forex_score, 0) >= 40
          AND (
              tier IN ('Tier_A', 'Tier_B', 'Tier_C')
              OR vip = TRUE
              OR account_management = TRUE
              OR copy_trading = TRUE
              OR funded_accounts = TRUE
              OR COALESCE(commercial_fit_score, 0) >= 40
          )
          AND (language = 'Arabic' OR COALESCE(arabic_ratio, 0) >= 15 OR COALESCE(arabic_score, 0) >= 20)
          AND (entity_type IS NULL OR entity_type != 'user')
          AND (outreach_priority_reason IS NULL OR outreach_priority_reason != 'user_account')
    ) as new_strict_qualified_count
FROM leads
WHERE discovered_at >= NOW() - INTERVAL '24 HOURS';
"""

cmd = [
    "ssh", "-i", REMOTE_KEY,
    "-o", "StrictHostKeyChecking=no",
    f"root@{REMOTE_HOST}",
    f"docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -x -c \"{sql}\""
]

res = subprocess.run(cmd, capture_output=True, text=True)
print(res.stdout)
if res.stderr:
    print("STDERR:", res.stderr)
