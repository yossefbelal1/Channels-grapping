import os
import sys
import subprocess

REMOTE_KEY = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"
REMOTE_HOST = "167.233.246.102"
REMOTE_USER = "root"

sql_script = """
-- 1. Explicitly reject AlWaheedAlKhorasani and any low-intent non-commercial channels
UPDATE leads
SET status = 'rejected'
WHERE channel_username = 'AlWaheedAlKhorasani';

-- 2. Clean up channels with 0 forex relevance and 0 commercial offerings
UPDATE leads
SET status = 'rejected'
WHERE status = 'new'
  AND COALESCE(forex_intent_score, forex_score, 0) < 40
  AND COALESCE(commercial_fit_score, 0) < 30
  AND vip = FALSE
  AND account_management = FALSE
  AND copy_trading = FALSE
  AND funded_accounts = FALSE
  AND tier = 'Tier_D';

-- 3. Detect and mark Account Management on leads with explicit account management keywords
UPDATE leads
SET account_management = TRUE,
    commercial_fit_score = GREATEST(COALESCE(commercial_fit_score, 0), 60),
    tier = CASE
        WHEN member_count >= 10000 AND COALESCE(forex_intent_score, forex_score, 0) >= 70 THEN 'Tier_A'::tier_level
        WHEN member_count >= 2000 AND COALESCE(forex_intent_score, forex_score, 0) >= 50 THEN 'Tier_B'::tier_level
        WHEN COALESCE(forex_intent_score, forex_score, 0) >= 40 THEN 'Tier_C'::tier_level
        ELSE COALESCE(tier, 'Tier_D'::tier_level)
    END
WHERE (
    description ~* '(إدارة حسابات|ادارة حسابات|إدارة الحسابات|ادارة الحسابات|اداره حسابات|إدارة محافظ|ادارة محافظ|إدارة المحافظ|ادارة المحافظ|اداره محافظ|إدارة الصفقات|ادارة الصفقات|تقاسم أرباح|نسبة أرباح)'
    OR title ~* '(إدارة حسابات|ادارة حسابات|إدارة الحسابات|ادارة الحسابات|ادارة محافظ|إدارة محافظ)'
)
AND COALESCE(forex_intent_score, forex_score, 0) >= 40;

-- 4. Detect and mark Copy Trading / Automated Bots on trading leads
UPDATE leads
SET copy_trading = TRUE,
    commercial_fit_score = GREATEST(COALESCE(commercial_fit_score, 0), 50),
    tier = CASE
        WHEN member_count >= 10000 AND COALESCE(forex_intent_score, forex_score, 0) >= 70 THEN 'Tier_A'::tier_level
        WHEN member_count >= 2000 AND COALESCE(forex_intent_score, forex_score, 0) >= 50 THEN 'Tier_B'::tier_level
        WHEN COALESCE(forex_intent_score, forex_score, 0) >= 40 THEN 'Tier_C'::tier_level
        ELSE COALESCE(tier, 'Tier_D'::tier_level)
    END
WHERE (
    description ~* '(نسخ تداول|نسخ صفقات|copy trading|copy trade|أنظمة تداول|انظمة تداول|بوت تداول|بوتات تداول|بوتات التداول|اكسبيرت)'
    OR title ~* '(نسخ تداول|نسخ صفقات|copy trading|بوتات التداول)'
)
AND COALESCE(forex_intent_score, forex_score, 0) >= 40;

-- 5. Detect and mark VIP / Premium Subscriptions on trading leads
UPDATE leads
SET vip = TRUE,
    commercial_fit_score = GREATEST(COALESCE(commercial_fit_score, 0), 40),
    tier = CASE
        WHEN member_count >= 10000 AND COALESCE(forex_intent_score, forex_score, 0) >= 70 THEN 'Tier_A'::tier_level
        WHEN member_count >= 2000 AND COALESCE(forex_intent_score, forex_score, 0) >= 50 THEN 'Tier_B'::tier_level
        WHEN COALESCE(forex_intent_score, forex_score, 0) >= 40 THEN 'Tier_C'::tier_level
        ELSE COALESCE(tier, 'Tier_D'::tier_level)
    END
WHERE (
    description ~* '(vip|قناة خاصة|قناه خاصه|توصيات خاصة|توصيات خاصه|قناة مدفوعة|باقة vip|باقات vip|اشتراك شهري|اشتراك vip)'
    OR title ~* '(vip|قناة خاصة|توصيات خاصة)'
)
AND COALESCE(forex_intent_score, forex_score, 0) >= 40;

-- 6. Recalculate 24h metrics verification
SELECT 
    COUNT(*) as total_discovered_24h,
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
    ) as qualified_count_24h
FROM leads
WHERE discovered_at >= NOW() - INTERVAL '24 HOURS';
"""

cmd = [
    "ssh", "-i", REMOTE_KEY,
    "-o", "StrictHostKeyChecking=no",
    f"{REMOTE_USER}@{REMOTE_HOST}",
    f"docker exec -i leadhunter_postgres psql -U postgres -d leadhunter_db"
]

res = subprocess.run(cmd, input=sql_script, capture_output=True, text=True, encoding="utf-8", errors="replace")
print("STDOUT:\n", res.stdout)
if res.stderr:
    print("STDERR:\n", res.stderr)
