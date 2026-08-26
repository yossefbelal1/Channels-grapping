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

print("--- Active Campaign ID ---")
print(run_ssh_query("SELECT id, status, created_at FROM campaigns WHERE status = 'active';").encode('ascii', errors='ignore').decode())

print("\n--- Total 'new' leads count ---")
print(run_ssh_query("SELECT COUNT(*) FROM leads WHERE status = 'new';"))

print("\n--- Unqueued 'new' leads count ---")
sql_unqueued = """
SELECT COUNT(*)
FROM leads l
WHERE l.status = 'new'
  AND l.contact_username IS NOT NULL
  AND l.contact_username != ''
  AND NOT EXISTS (
      SELECT 1 FROM campaign_logs cl WHERE cl.lead_id = l.id
  );
"""
print(run_ssh_query(sql_unqueued))

print("\n--- Unqueued unique contact 'new' leads count ---")
sql_unqueued_unique_contact = """
SELECT COUNT(DISTINCT l.id)
FROM leads l
WHERE l.status = 'new'
  AND l.contact_username IS NOT NULL
  AND l.contact_username != ''
  AND NOT EXISTS (
      SELECT 1 FROM campaign_logs cl
      JOIN leads l2 ON cl.lead_id = l2.id
      WHERE LOWER(l2.contact_username) = LOWER(l.contact_username)
  );
"""
print(run_ssh_query(sql_unqueued_unique_contact))
