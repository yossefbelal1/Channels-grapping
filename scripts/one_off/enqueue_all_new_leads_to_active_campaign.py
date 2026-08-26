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

print("--- Enqueuing all newly discovered unique leads into active campaign ---")
sql_enqueue_missing = """
INSERT INTO campaign_logs (id, campaign_id, lead_id, status, sent_at)
SELECT gen_random_uuid(), c.id, l.id, 'pending', NULL
FROM leads l
CROSS JOIN (SELECT id FROM campaigns WHERE status = 'active' ORDER BY created_at DESC LIMIT 1) c
WHERE l.status = 'new'
  AND l.contact_username IS NOT NULL
  AND l.contact_username != ''
  AND NOT EXISTS (
      SELECT 1
      FROM campaign_logs cl2
      JOIN leads l2 ON cl2.lead_id = l2.id
      WHERE LOWER(l2.contact_username) = LOWER(l.contact_username)
  );
"""
print(run_ssh_query(sql_enqueue_missing))

print("\n--- Campaign Stats After Enqueue ---")
sql_stats = """
SELECT c.id,
       COUNT(cl.id) as total_recipients,
       COUNT(cl.id) FILTER (WHERE cl.status = 'sent') as sent,
       COUNT(cl.id) FILTER (WHERE cl.status = 'failed') as failed,
       COUNT(cl.id) FILTER (WHERE cl.status = 'skipped') as skipped,
       COUNT(cl.id) FILTER (WHERE cl.status = 'pending') as pending
FROM campaigns c
LEFT JOIN campaign_logs cl ON c.id = cl.campaign_id
WHERE c.status = 'active'
GROUP BY c.id;
"""
print(run_ssh_query(sql_stats))
