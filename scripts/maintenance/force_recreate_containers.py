import paramiko
import sys
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path)

print("=== Stopping old containers and recreating with fresh image ===")
cmd = "cd /root/Channels-grapping && docker compose build worker_validator dashboard && docker compose up -d --force-recreate worker_validator dashboard"
stdin, stdout, stderr = ssh.exec_command(cmd)
print(stdout.read().decode())
print(stderr.read().decode())

stdin, stdout, stderr = ssh.exec_command('docker ps --filter "name=worker_validator" --filter "name=leadhunter_dashboard"')
print("=== Container Status ===")
print(stdout.read().decode())

stdin, stdout, stderr = ssh.exec_command('docker logs --tail 30 worker_validator')
print("=== New worker_validator logs ===")
print(stdout.read().decode())

ssh.close()
