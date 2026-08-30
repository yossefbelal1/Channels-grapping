import paramiko
import sys
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path)

cmd1 = 'docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'
stdin, stdout, stderr = ssh.exec_command(cmd1)
print("=== Running Docker Containers ===")
print(stdout.read().decode())

cmd2 = 'docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "SELECT id, created_at, status, message_text FROM campaigns ORDER BY created_at DESC LIMIT 5;"'
stdin, stdout, stderr = ssh.exec_command(cmd2)
print("=== Active Campaigns ===")
print(stdout.read().decode())

cmd3 = 'docker exec leadhunter_redis redis-cli keys "*campaign*"'
stdin, stdout, stderr = ssh.exec_command(cmd3)
print("=== Redis Campaign Keys ===")
print(stdout.read().decode())

cmd4 = 'docker exec leadhunter_redis redis-cli keys "*health*"'
stdin, stdout, stderr = ssh.exec_command(cmd4)
print("=== Redis Health / Rate Limit Keys ===")
print(stdout.read().decode())

cmd5 = 'docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "SELECT count(*) FROM leads WHERE contact_username IS NOT NULL AND contact_username != \'\' AND status != \'rejected\';"'
stdin, stdout, stderr = ssh.exec_command(cmd5)
print("=== Qualified Leads with Contact Username ===")
print(stdout.read().decode())

ssh.close()
