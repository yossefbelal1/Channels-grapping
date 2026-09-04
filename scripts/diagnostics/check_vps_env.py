import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path, timeout=10)

cmd = "grep -E 'OUTREACH|CAMPAIGN' /root/Channels-grapping/.env || echo 'No OUTREACH variables in .env'"
stdin, stdout, stderr = ssh.exec_command(cmd)
print("=== Current Outreach Env on VPS ===")
print(stdout.read().decode())

ssh.close()
