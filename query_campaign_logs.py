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

print("--- Campaign logs grouped by status directly in DB ---")
print(run_ssh_query("SELECT status, COUNT(*) FROM campaign_logs GROUP BY status;"))

print("--- Checking for active outreach worker logs ---")
cmd_logs = [
    "ssh", "-o", "StrictHostKeyChecking=no", "-i", key_path,
    f"root@{new_ip}",
    "docker logs --tail 30 worker_validator 2>&1"
]
res_logs = subprocess.run(cmd_logs, capture_output=True)
print((res_logs.stdout or b"").decode("utf-8", errors="replace"))
