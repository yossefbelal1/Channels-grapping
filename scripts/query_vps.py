import sys
import subprocess

if len(sys.argv) < 2:
    print("Usage: python scripts/query_vps.py \"<SQL_OR_COMMAND>\"")
    sys.exit(1)

arg = sys.argv[1]
pem = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"
host = "root@167.233.246.102"

if arg.upper().startswith("SELECT") or arg.upper().startswith("UPDATE") or arg.upper().startswith("DELETE"):
    cmd = ["ssh", "-i", pem, "-o", "StrictHostKeyChecking=no", host, f"docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c \"{arg}\""]
else:
    cmd = ["ssh", "-i", pem, "-o", "StrictHostKeyChecking=no", host, arg]

res = subprocess.run(cmd, capture_output=True, text=True)
print(res.stdout)
if res.stderr:
    print("STDERR:", res.stderr, file=sys.stderr)
