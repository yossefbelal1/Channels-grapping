import paramiko
import sys
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path)

stdin, stdout, stderr = ssh.exec_command('docker ps --filter "name=worker_" --filter "name=leadhunter_"')
print("=== Container Status ===")
print(stdout.read().decode('utf-8', errors='replace'))

stdin, stdout, stderr = ssh.exec_command('docker logs --tail 30 worker_validator 2>&1')
print("=== worker_validator logs ===")
print(stdout.read().decode('utf-8', errors='replace'))

stdin, stdout, stderr = ssh.exec_command('docker logs --tail 30 worker_graph_expander 2>&1')
print("=== worker_graph_expander logs ===")
print(stdout.read().decode('utf-8', errors='replace'))

stdin, stdout, stderr = ssh.exec_command('docker logs --tail 25 worker_radar 2>&1')
print("=== worker_radar logs ===")
print(stdout.read().decode('utf-8', errors='replace'))

stdin, stdout, stderr = ssh.exec_command('docker logs --tail 25 worker_scavenger 2>&1')
print("=== worker_scavenger logs ===")
print(stdout.read().decode('utf-8', errors='replace'))

stdin, stdout, stderr = ssh.exec_command('docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "SELECT status, count(*) FROM campaign_logs GROUP BY status;"')
print("=== Database Campaign Status Breakdown ===")
print(stdout.read().decode('utf-8', errors='replace'))

ssh.close()
