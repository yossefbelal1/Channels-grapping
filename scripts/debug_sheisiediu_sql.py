import subprocess

REMOTE_KEY = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"
REMOTE_HOST = "167.233.246.102"

sql = """
SELECT 
    channel_username,
    status = 'new' as c1_status_new,
    COALESCE(forex_intent_score, forex_score, 0) >= 40 as c2_forex_40,
    tier IN ('Tier_A', 'Tier_B', 'Tier_C') as c3_tier_abc,
    vip as c3_vip,
    account_management as c3_ac,
    copy_trading as c3_cp,
    funded_accounts as c3_funded,
    COALESCE(commercial_fit_score, 0) >= 40 as c3_comm_40,
    (
        tier IN ('Tier_A', 'Tier_B', 'Tier_C')
        OR vip = TRUE
        OR account_management = TRUE
        OR copy_trading = TRUE
        OR funded_accounts = TRUE
        OR COALESCE(commercial_fit_score, 0) >= 40
    ) as c3_commercial_overall,
    (language = 'Arabic' OR COALESCE(arabic_ratio, 0) >= 15 OR COALESCE(arabic_score, 0) >= 20) as c4_arabic
FROM leads 
WHERE channel_username = 'sheisiediu';
"""

cmd = [
    "ssh", "-i", REMOTE_KEY,
    "-o", "StrictHostKeyChecking=no",
    f"root@{REMOTE_HOST}",
    f"docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -x -c \"{sql}\""
]

res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print(res.stdout)
