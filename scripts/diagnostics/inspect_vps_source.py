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

run("ls -la /root/Channels-grapping", "ls /root/Channels-grapping")
run('find / -maxdepth 4 -name ".git" 2>/dev/null', "Find all git repositories")
run("cat /root/Channels-grapping/.env | grep -v 'KEY\\|HASH\\|PASS' | head -n 30", "/root/Channels-grapping/.env (masked)")
run("docker inspect worker_validator --format 'Image: {{.Image}} | Created: {{.Created}}'", "worker_validator Image info")

ssh.close()
