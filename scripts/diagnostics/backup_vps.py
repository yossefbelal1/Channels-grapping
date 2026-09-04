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

# 1. Take a full database backup before running any migrations!
backup_cmd = 'docker exec leadhunter_postgres pg_dump -U postgres leadhunter_db > /root/backup_leadhunter_db_$(date +%Y%m%d_%H%M%S).sql && ls -lh /root/backup_leadhunter_db_*.sql | tail -n 1'
run(backup_cmd, "PostgreSQL Backup")

# 2. Backup the directory /root/Channels-grapping as well
run('tar -czf /root/backup_Channels_grapping_$(date +%Y%m%d_%H%M%S).tar.gz -C /root Channels-grapping && ls -lh /root/backup_Channels_grapping_*.tar.gz | tail -n 1', "Directory Backup")

ssh.close()
