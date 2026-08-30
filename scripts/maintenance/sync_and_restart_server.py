import os
import paramiko
import sys
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path)

local_dir = r'c:\Users\NV LAP\Downloads\Phone Link\Channels-grapping'
remote_dir = '/root/Channels-grapping'

files_to_sync = [
    'validator.py',
    'dashboard.py',
    'campaign_worker.py',
    'tg_manager.py',
    'radar.py',
    'scavenger.py',
    'graph_expander.py',
    'seed_intake_worker.py',
    'web_scraper.py',
    'keyword_frequency_service.py',
    'schema.sql',
    'requirements.txt',
    'Dockerfile',
    'docker-compose.yml',
    'docker-compose.dev.yml',
]

sftp = ssh.open_sftp()
for f in files_to_sync:
    local_path = os.path.join(local_dir, f)
    remote_path = f"{remote_dir}/{f}"
    if os.path.exists(local_path):
        try:
            with open(local_path, 'rb') as lf:
                with sftp.open(remote_path, 'wb') as rf:
                    rf.write(lf.read())
            print(f"Synced: {f}")
        except Exception as e:
            print(f"Error syncing {f}: {e}")

# Ensure app directories exist
ssh.exec_command('mkdir -p /root/Channels-grapping/app/core')

for root, dirs, files in os.walk(os.path.join(local_dir, 'app')):
    rel_dir = os.path.relpath(root, local_dir).replace('\\', '/')
    ssh.exec_command(f'mkdir -p /root/Channels-grapping/{rel_dir}')
    for file in files:
        if file.endswith('.py'):
            l_file = os.path.join(root, file)
            r_file = f"{remote_dir}/{rel_dir}/{file}"
            with open(l_file, 'rb') as lf:
                with sftp.open(r_file, 'wb') as rf:
                    rf.write(lf.read())
            print(f"Synced: {rel_dir}/{file}")

sftp.close()

print("=== Rebuilding docker images ===")
cmd_build = 'cd /root/Channels-grapping && docker compose build worker_validator dashboard'
stdin, stdout, stderr = ssh.exec_command(cmd_build)
print(stdout.read().decode())
print(stderr.read().decode())

print("=== Starting updated containers ===")
cmd_up = 'cd /root/Channels-grapping && docker compose up -d worker_validator dashboard'
stdin, stdout, stderr = ssh.exec_command(cmd_up)
print(stdout.read().decode())
print(stderr.read().decode())

print("=== Verifying running containers ===")
cmd_ps = 'docker ps --filter "name=worker_validator" --filter "name=leadhunter_dashboard"'
stdin, stdout, stderr = ssh.exec_command(cmd_ps)
print(stdout.read().decode())

ssh.close()
