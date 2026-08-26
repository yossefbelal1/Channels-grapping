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

print("--- Total Leads Count ---")
print(run_ssh_query("SELECT COUNT(*) FROM leads;"))

print("--- Leads grouped by Status and Tier ---")
print(run_ssh_query("SELECT status, tier, COUNT(*) FROM leads GROUP BY status, tier ORDER BY count DESC;"))

print("--- Leads count in dashboard.py query logic ---")
print(run_ssh_query("SELECT COUNT(*) FROM leads WHERE status != 'rejected';"))
