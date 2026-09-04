import paramiko
import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path, timeout=10)

print("1. Recreating worker_validator with new .env and updated code...")
# Copy files into container volume or recreate container
cmd = """
cd /root/Channels-grapping && docker-compose up -d --no-deps --build worker_validator
"""
stdin, stdout, stderr = ssh.exec_command(cmd)
print("Docker compose output:")
print(stdout.read().decode())
print("Stderr if any:", stderr.read().decode())

print("2. Waiting 20s for worker_validator to initialize...")
time.sleep(20)

cmd = "docker logs --tail 40 worker_validator 2>&1"
stdin, stdout, stderr = ssh.exec_command(cmd)
print("=== worker_validator recent logs ===")
print(stdout.read().decode())

ssh.close()
