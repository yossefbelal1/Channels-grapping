import paramiko
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path, timeout=10)

cmd = 'docker ps -a --filter "name=worker_validator" --format "table {{.Names}}\t{{.Status}}\t{{.Command}}"'
stdin, stdout, stderr = ssh.exec_command(cmd)
print("=== Status ===")
print(stdout.read().decode())

cmd = "docker logs --tail 30 worker_validator 2>&1"
stdin, stdout, stderr = ssh.exec_command(cmd)
print("=== worker_validator recent logs (2>&1) ===")
print(stdout.read().decode())

ssh.close()
