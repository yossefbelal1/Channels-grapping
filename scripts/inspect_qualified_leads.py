import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

REMOTE_KEY = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"
REMOTE_HOST = "167.233.246.102"

sql = """
SELECT channel_username, member_count, forex_intent_score, commercial_fit_score, vip, account_management, copy_trading, tier, contact_username, admin_username
FROM leads
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
ORDER BY member_count DESC NULLS LAST;
"""

cmd = [
    "ssh", "-i", REMOTE_KEY,
    "-o", "StrictHostKeyChecking=no",
    f"root@{REMOTE_HOST}",
    f"docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c \"{sql}\""
]

res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print(res.stdout)
if res.stderr:
    print("STDERR:", res.stderr)
