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

print("--- Querying leads for abrahim151515 ---")
print(run_ssh_query("SELECT id, channel_username, contact_username, status FROM leads WHERE LOWER(contact_username) LIKE '%abrahim151515%';"))

print("--- Querying campaign_logs for abrahim151515 ---")
print(run_ssh_query("SELECT cl.id, cl.campaign_id, cl.lead_id, cl.status, cl.sent_at, l.channel_username, l.contact_username FROM campaign_logs cl JOIN leads l ON cl.lead_id = l.id WHERE LOWER(l.contact_username) LIKE '%abrahim151515%';"))

print("--- Checking duplicate contact_usernames in campaign_logs ---")
print(run_ssh_query("""
SELECT LOWER(l.contact_username) as contact, COUNT(*) as send_attempts, COUNT(*) FILTER (WHERE cl.status = 'sent') as sent_count
FROM campaign_logs cl
JOIN leads l ON cl.lead_id = l.id
WHERE l.contact_username IS NOT NULL AND l.contact_username != ''
GROUP BY LOWER(l.contact_username)
HAVING COUNT(*) > 1
ORDER BY send_attempts DESC
LIMIT 20;
"""))
