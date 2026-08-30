import paramiko
import sys
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path)

cmd1 = 'docker exec leadhunter_redis redis-cli get "health:user_session:rate_limited_until"'
stdin, stdout, stderr = ssh.exec_command(cmd1)
print("=== user_session rate_limited_until ===")
print(stdout.read().decode())

cmd2 = 'docker logs --tail 80 worker_validator'
stdin, stdout, stderr = ssh.exec_command(cmd2)
print("=== worker_validator tail logs ===")
print(stdout.read().decode())

# Check pending logs breakdown: how many have contact_username vs null
cmd3 = 'docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "SELECT count(*) FILTER (WHERE l.contact_username IS NOT NULL AND l.contact_username != \'\') as has_contact, count(*) FILTER (WHERE l.contact_username IS NULL OR l.contact_username = \'\') as no_contact FROM campaign_logs cl JOIN leads l ON cl.lead_id = l.id WHERE cl.status = \'pending\';"'
stdin, stdout, stderr = ssh.exec_command(cmd3)
print("=== Pending Campaign Logs Breakdown ===")
print(stdout.read().decode())

# Check daily sent count in Redis
cmd4 = 'docker exec leadhunter_redis redis-cli keys "*sent*"'
stdin, stdout, stderr = ssh.exec_command(cmd4)
print("=== Sent Keys in Redis ===")
print(stdout.read().decode())

ssh.close()
