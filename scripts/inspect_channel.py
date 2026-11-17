import subprocess

REMOTE_KEY = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"
REMOTE_HOST = "167.233.246.102"
sql = "SELECT * FROM leads WHERE channel_username = 'AlWaheedAlKhorasani';"
cmd = ["ssh", "-i", REMOTE_KEY, "-o", "StrictHostKeyChecking=no", f"root@{REMOTE_HOST}", f"docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -x -c \"{sql}\""]
res = subprocess.run(cmd, capture_output=True, text=True)
print(res.stdout)
