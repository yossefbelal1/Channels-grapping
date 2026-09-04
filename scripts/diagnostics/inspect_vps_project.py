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

# 1. Find the project directory
run('docker inspect worker_validator --format "{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}"', "Validator Mounts")
run('docker inspect worker_validator --format "{{.Config.WorkingDir}} | {{.Config.Cmd}}"', "Validator WorkingDir")
run('find / -maxdepth 3 -type d -name "*Channels*" 2>/dev/null; find /root /home /var -maxdepth 2 -name "docker-compose.yml" 2>/dev/null', "Search Project Dirs")

ssh.close()
