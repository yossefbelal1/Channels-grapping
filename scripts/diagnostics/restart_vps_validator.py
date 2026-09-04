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

print("=== Restarting worker_validator with updated codebase ===")
stdin, stdout, stderr = ssh.exec_command("docker restart worker_validator")
print("Restart:", stdout.read().decode().strip())

print("Waiting 15 seconds for startup...")
time.sleep(15)

cmd = "docker logs --tail 40 worker_validator 2>&1"
stdin, stdout, stderr = ssh.exec_command(cmd)
print("=== worker_validator startup logs ===")
print(stdout.read().decode())

ssh.close()
