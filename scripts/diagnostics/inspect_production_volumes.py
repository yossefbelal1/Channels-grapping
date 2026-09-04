import paramiko
import sys
import os

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path, timeout=10)

def run(cmd, label):
    print(f"\n{'='*20} {label} {'='*20}")
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out:
        print(out)
    if err:
        print(f"[STDERR]: {err}")
    return out

run("docker volume ls | grep channels", "Docker Volumes")
run("docker inspect leadhunter_postgres --format '{{range .Mounts}}{{.Name}} -> {{.Destination}}{{println}}{{end}}'", "Postgres Mounts")
run("docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c '\dt'", "Database Tables in leadhunter_db")
run("docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c 'SELECT count(*) FROM leads; SELECT count(*) FROM campaigns; SELECT count(*) FROM campaign_logs;'", "Row Counts in Tables")

ssh.close()
