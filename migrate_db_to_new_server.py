import subprocess
import time

old_ip = "63.178.198.95"
new_ip = "167.233.246.102"
key_path = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"
dump_local = r"c:\Users\NV LAP\Downloads\Phone Link\Channels-grapping\leadhunter_db_dump.sql"

print(f"1. Dumping PostgreSQL database from old server (ubuntu@{old_ip})...")
dump_cmd = [
    "ssh", "-o", "StrictHostKeyChecking=no", "-i", key_path,
    f"ubuntu@{old_ip}",
    "sudo docker exec -i leadhunter_postgres pg_dump -U postgres leadhunter_db"
]

with open(dump_local, "w", encoding="utf-8") as f:
    res = subprocess.run(dump_cmd, stdout=f, stderr=subprocess.PIPE, text=True)

if res.returncode != 0:
    print("Database dump failed:", res.stderr)
else:
    print("Database dump successfully saved to local file!")

print(f"2. Transferring database dump to new server (root@{new_ip})...")
scp_cmd = [
    "scp", "-o", "StrictHostKeyChecking=no", "-i", key_path,
    dump_local,
    f"root@{new_ip}:/tmp/leadhunter_db_dump.sql"
]

res_scp = subprocess.run(scp_cmd, capture_output=True, text=True)
if res_scp.returncode != 0:
    print("SCP transfer failed:", res_scp.stderr)
else:
    print("Database dump transferred to new server /tmp/leadhunter_db_dump.sql successfully!")
