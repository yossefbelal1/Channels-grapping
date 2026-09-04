import paramiko
import sys

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path, timeout=10)

# Replace SESSION_VALIDATOR=validator_session with SESSION_VALIDATOR=user_session
cmd = """
sed -i 's/SESSION_VALIDATOR=.*/SESSION_VALIDATOR=user_session/g' /root/Channels-grapping/.env
grep 'SESSION_VALIDATOR' /root/Channels-grapping/.env
"""
stdin, stdout, stderr = ssh.exec_command(cmd)
print("=== Updated SESSION_VALIDATOR on VPS ===")
print(stdout.read().decode())

ssh.close()
