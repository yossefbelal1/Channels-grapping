import paramiko
import sys

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path, timeout=10)

cmd = "docker exec worker_validator ls -la /app/sessions"
stdin, stdout, stderr = ssh.exec_command(cmd)
print("=== Telegram Sessions in worker_validator ===")
print(stdout.read().decode())

ssh.close()
