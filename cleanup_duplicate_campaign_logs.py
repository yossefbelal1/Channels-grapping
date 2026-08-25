import subprocess

key_path = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"
new_ip = "167.233.246.102"

def run_ssh_query(sql):
    cmd = [
        "ssh", "-o", "StrictHostKeyChecking=no", "-i", key_path,
        f"root@{new_ip}",
        f"docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c \"{sql}\""
    ]
    res = subprocess.run(cmd, capture_output=True)
    return (res.stdout or b"").decode("utf-8", errors="replace")

print("--- Step 1: Mark pending logs as 'skipped' for contact_usernames that ALREADY received a 'sent' message ---")
sql_skip_sent = """
UPDATE campaign_logs cl
SET status = 'skipped',
    error_message = 'Skipped: Contact username already messaged',
    sent_at = NOW()
FROM leads l
WHERE cl.lead_id = l.id
  AND cl.status = 'pending'
  AND l.contact_username IS NOT NULL
  AND l.contact_username != ''
  AND EXISTS (
      SELECT 1
      FROM campaign_logs cl2
      JOIN leads l2 ON cl2.lead_id = l2.id
      WHERE LOWER(l2.contact_username) = LOWER(l.contact_username)
        AND cl2.status = 'sent'
  );
"""
print(run_ssh_query(sql_skip_sent))

print("\n--- Step 2: For contacts with multiple pending logs, keep only 1 pending log and mark duplicates as 'skipped' ---")
sql_skip_pending_dups = """
WITH ranked_pending AS (
    SELECT cl.id,
           ROW_NUMBER() OVER (PARTITION BY LOWER(l.contact_username) ORDER BY cl.id) as rn
    FROM campaign_logs cl
    JOIN leads l ON cl.lead_id = l.id
    WHERE cl.status = 'pending'
      AND l.contact_username IS NOT NULL
      AND l.contact_username != ''
)
UPDATE campaign_logs
SET status = 'skipped',
    error_message = 'Skipped: Duplicate pending contact in queue',
    sent_at = NOW()
WHERE id IN (
    SELECT id FROM ranked_pending WHERE rn > 1
);
"""
print(run_ssh_query(sql_skip_pending_dups))

print("\n--- Verification: Checking abrahim151515 status ---")
print(run_ssh_query("""
SELECT cl.id, cl.status, cl.error_message, l.channel_username, l.contact_username
FROM campaign_logs cl
JOIN leads l ON cl.lead_id = l.id
WHERE LOWER(l.contact_username) LIKE '%abrahim151515%';
"""))

print("\n--- Verification: Duplicate contacts summary in campaign_logs ---")
print(run_ssh_query("""
SELECT LOWER(l.contact_username) as contact,
       COUNT(*) as total_logs,
       COUNT(*) FILTER (WHERE cl.status = 'sent') as sent_count,
       COUNT(*) FILTER (WHERE cl.status = 'pending') as pending_count,
       COUNT(*) FILTER (WHERE cl.status = 'skipped') as skipped_count
FROM campaign_logs cl
JOIN leads l ON cl.lead_id = l.id
WHERE l.contact_username IS NOT NULL AND l.contact_username != ''
GROUP BY LOWER(l.contact_username)
HAVING COUNT(*) FILTER (WHERE cl.status = 'pending') > 1
ORDER BY total_logs DESC;
"""))
