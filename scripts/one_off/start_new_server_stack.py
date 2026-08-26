import subprocess
import time

new_ip = "167.233.246.102"
key_path = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"

def run_ssh(cmd):
    full_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-i", key_path, f"root@{new_ip}", cmd]
    res = subprocess.run(full_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"SSH Error ({cmd}):", res.stderr)
    return res.stdout

print("1. Starting PostgreSQL & Redis containers...")
print(run_ssh("cd /root/Channels-grapping && docker compose up -d postgres redis"))

print("Waiting 5 seconds for PostgreSQL container initialization...")
time.sleep(5)

print("2. Restoring PostgreSQL database dump (16MB)...")
restore_cmd = "docker exec -i leadhunter_postgres psql -U postgres -d leadhunter_db < /tmp/leadhunter_db_dump.sql"
print(run_ssh(f"cd /root/Channels-grapping && {restore_cmd}"))

print("3. Launching full LeadHunter Docker Stack...")
print(run_ssh("cd /root/Channels-grapping && docker compose up -d --build"))

print("4. Checking running containers...")
print(run_ssh("docker ps"))

print("5. Verifying restored leads count...")
print(run_ssh("docker exec -i leadhunter_postgres psql -U postgres -d leadhunter_db -c 'SELECT COUNT(*) FROM leads;'"))
