import subprocess

REMOTE_KEY = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"
REMOTE_HOST = "167.233.246.102"

sql = "SELECT channel_username, title, member_count, forex_intent_score, commercial_fit_score, vip, account_management, copy_trading, funded_accounts, tier, language, arabic_ratio, arabic_score FROM leads WHERE channel_username = 'sheisiediu';"

cmd = [
    "ssh", "-i", REMOTE_KEY,
    "-o", "StrictHostKeyChecking=no",
    f"root@{REMOTE_HOST}",
    f"docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -x -c \"{sql}\""
]

res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print(res.stdout)
