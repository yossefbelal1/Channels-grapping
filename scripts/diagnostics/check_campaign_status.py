import subprocess

key_path = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"
new_ip = "167.233.246.102"

def run_ssh(cmd):
    full_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-i", key_path, f"root@{new_ip}", cmd]
    res = subprocess.run(full_cmd, capture_output=True)
    out = (res.stdout or b"").decode("utf-8", errors="replace")
    err = (res.stderr or b"").decode("utf-8", errors="replace")
    return out + err

print("=== 1. Active Campaigns ===")
print(run_ssh("docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c 'SELECT id, status, created_at FROM campaigns ORDER BY created_at DESC LIMIT 5;'"))

print("=== 2. Campaign Logs Summary ===")
print(run_ssh("docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c 'SELECT status, COUNT(*) FROM campaign_logs GROUP BY status;'"))

print("=== 3. Sessions directory ===")
print(run_ssh("ls -la /root/Channels-grapping/sessions/"))

print("=== 4. user_session file check ===")
print(run_ssh("ls -la /root/Channels-grapping/*.session 2>/dev/null || echo 'No .session files in root dir'"))

print("=== 5. Check accounts.json content ===")
print(run_ssh("cat /root/Channels-grapping/accounts.json"))
