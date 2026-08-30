import paramiko
import sys
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path)

cmd1 = 'find /root -maxdepth 3 -name "docker-compose.yml" -o -name ".git"'
stdin, stdout, stderr = ssh.exec_command(cmd1)
print("=== Compose and Git repos on server ===")
print(stdout.read().decode())

cmd2 = 'docker compose -f /root/Channels-grapping/docker-compose.yml config --services'
stdin, stdout, stderr = ssh.exec_command(cmd2)
print("=== Services in /root/Channels-grapping/docker-compose.yml ===")
print(stdout.read().decode())

ssh.close()
