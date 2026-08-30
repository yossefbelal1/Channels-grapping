import paramiko
import sys
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path)

cmd1 = 'docker exec worker_validator ps aux'
stdin, stdout, stderr = ssh.exec_command(cmd1)
print("=== worker_validator processes ===")
print(stdout.read().decode())

cmd2 = 'docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "SELECT count(*) FROM campaign_logs cl JOIN leads l ON cl.lead_id = l.id WHERE cl.status = \'failed\' AND l.contact_username IS NOT NULL AND l.contact_username != \'\';"'
stdin, stdout, stderr = ssh.exec_command(cmd2)
print("=== Failed Logs that now HAVE a contact_username ===")
print(stdout.read().decode())

cmd3 = 'docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "SELECT cl.id, l.channel_username, l.contact_username, cl.error_message FROM campaign_logs cl JOIN leads l ON cl.lead_id = l.id WHERE cl.status = \'failed\' AND l.contact_username IS NOT NULL AND l.contact_username != \'\' LIMIT 20;"'
stdin, stdout, stderr = ssh.exec_command(cmd3)
print("=== Sample of Failed Logs with contact_username ===")
print(stdout.read().decode())

ssh.close()
