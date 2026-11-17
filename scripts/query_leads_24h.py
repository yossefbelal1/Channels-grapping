import subprocess

REMOTE_KEY = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"
REMOTE_HOST = "167.233.246.102"

sql = """
SELECT channel_username, member_count, forex_intent_score, forex_score, commercial_fit_score, vip, account_management, copy_trading, tier, status
FROM leads
WHERE discovered_at >= NOW() - INTERVAL '24 HOURS' AND status = 'new'
ORDER BY discovered_at DESC
LIMIT 40;
"""

cmd = [
    "ssh", "-i", REMOTE_KEY,
    "-o", "StrictHostKeyChecking=no",
    f"root@{REMOTE_HOST}",
    f"docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c \"{sql}\""
]

res = subprocess.run(cmd, capture_output=True, text=True)
print(res.stdout)
if res.stderr:
    print("STDERR:", res.stderr)
