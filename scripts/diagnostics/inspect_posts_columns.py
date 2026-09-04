import paramiko
import sys

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path, timeout=10)

cmd = """docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'channel_posts' 
ORDER BY ordinal_position;
" """
stdin, stdout, stderr = ssh.exec_command(cmd)
print("=== Columns in channel_posts table on VPS ===")
print(stdout.read().decode())

ssh.close()
