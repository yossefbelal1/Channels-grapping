import paramiko
import sys
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path)

cmd1 = 'docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "SELECT cl.id, cl.status, cl.error_message, cl.sent_at, l.channel_username, l.contact_username FROM campaign_logs cl JOIN leads l ON cl.lead_id = l.id WHERE cl.status = \'failed\' ORDER BY cl.sent_at DESC NULLS FIRST LIMIT 5;"'
stdin, stdout, stderr = ssh.exec_command(cmd1)
print("=== Latest Failed Log ===")
print(stdout.read().decode())

cmd2 = 'docker logs worker_validator'
stdin, stdout, stderr = ssh.exec_command(cmd2)
print("=== worker_validator full docker logs ===")
print(stdout.read().decode())

ssh.close()
