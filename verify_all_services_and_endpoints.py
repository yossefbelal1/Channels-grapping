import subprocess

key_path = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"
new_ip = "167.233.246.102"

def run_ssh_cmd(cmd_str):
    cmd = [
        "ssh", "-o", "StrictHostKeyChecking=no", "-i", key_path,
        f"root@{new_ip}",
        cmd_str
    ]
    res = subprocess.run(cmd, capture_output=True)
    return (res.stdout or b"").decode("utf-8", errors="replace"), (res.stderr or b"").decode("utf-8", errors="replace")

print("--- 1. Testing LeadHunter Dashboard API (/api/leads & /api/campaigns) ---")
out1, _ = run_ssh_cmd("curl -s http://127.0.0.1:8000/api/quality_stats")
print("LeadHunter API Response Snippet:", out1[:200])

print("\n--- 2. Testing SaaS FastAPI API (/api/v1/health or /docs or /) ---")
out2, _ = run_ssh_cmd("curl -s -I http://127.0.0.1:8001/")
print("SaaS API Header Response:", out2.splitlines()[0] if out2 else "No response")

print("\n--- 3. Testing SaaS Frontend (Port 3000) ---")
out3, _ = run_ssh_cmd("curl -s -I http://127.0.0.1:3000/")
print("SaaS Frontend Response:", out3.splitlines()[0] if out3 else "No response")

print("\n--- 4. Testing NGINX Web Server (Port 80) ---")
out4, _ = run_ssh_cmd("curl -s -I -H 'Host: telegauto.com' http://127.0.0.1:80/")
print("NGINX Web Server Response:", out4.splitlines()[0] if out4 else "No response")

print("\n--- 5. Checking DB & Redis Connections for both stacks ---")
out5, _ = run_ssh_cmd("docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c 'SELECT COUNT(*) FROM leads;'")
print("LeadHunter DB Check:", out5.strip())

out6, _ = run_ssh_cmd("docker exec saas_postgres psql -U postgres -d postgres -c 'SELECT 1;' 2>/dev/null || docker exec saas_postgres psql -U postgres -c 'SELECT 1;'")
print("SaaS DB Check:", out6.strip())

out7, _ = run_ssh_cmd("docker exec leadhunter_redis redis-cli ping")
print("LeadHunter Redis Check:", out7.strip())

out8, _ = run_ssh_cmd("docker exec saas_redis redis-cli ping")
print("SaaS Redis Check:", out8.strip())

print("\n--- 6. Checking Container Status Summary ---")
out9, _ = run_ssh_cmd("docker ps --format '{{.Names}}: {{.Status}}'")
print(out9.strip())
