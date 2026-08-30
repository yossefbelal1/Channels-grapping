import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path)

cmd1 = 'docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "SELECT status, count(*) FROM campaign_logs GROUP BY status;"'
stdin, stdout, stderr = ssh.exec_command(cmd1)
print("=== Status Breakdown ===")
print(stdout.read().decode())

cmd2 = 'docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "SELECT error_message, count(*) FROM campaign_logs WHERE status = \'failed\' GROUP BY error_message ORDER BY count(*) DESC LIMIT 20;"'
stdin, stdout, stderr = ssh.exec_command(cmd2)
print("=== Top Failed Error Messages ===")
print(stdout.read().decode())

cmd3 = 'docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "SELECT cl.id, cl.status, cl.error_message, cl.sent_at, l.channel_username, l.contact_username FROM campaign_logs cl JOIN leads l ON cl.lead_id = l.id WHERE cl.status = \'failed\' ORDER BY cl.sent_at DESC NULLS FIRST LIMIT 15;"'
stdin, stdout, stderr = ssh.exec_command(cmd3)
print("=== Latest Failed Logs ===")
print(stdout.read().decode())

# Check container logs
cmd4 = 'docker logs --tail 50 worker_validator'
stdin, stdout, stderr = ssh.exec_command(cmd4)
print("=== worker_validator recent logs ===")
print(stdout.read().decode())

ssh.close()
