import paramiko
import sys
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path)

stdin, stdout, stderr = ssh.exec_command('docker ps --filter "name=worker_validator" --filter "name=leadhunter_dashboard"')
print("=== Container Status ===")
print(stdout.read().decode())

stdin, stdout, stderr = ssh.exec_command('docker logs --tail 40 worker_validator')
print("=== worker_validator logs ===")
print(stdout.read().decode())

stdin, stdout, stderr = ssh.exec_command('docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "SELECT status, count(*) FROM campaign_logs GROUP BY status;"')
print("=== Database Campaign Status Breakdown ===")
print(stdout.read().decode())

ssh.close()
