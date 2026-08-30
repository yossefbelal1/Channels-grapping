import paramiko
import sys
import requests
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path)

# Sync dashboard.py
sftp = ssh.open_sftp()
local_path = r'c:\Users\NV LAP\Downloads\Phone Link\Channels-grapping\dashboard.py'
remote_path = '/root/Channels-grapping/dashboard.py'
with open(local_path, 'rb') as lf:
    with sftp.open(remote_path, 'wb') as rf:
        rf.write(lf.read())
print("Uploaded fixed dashboard.py to server.")
sftp.close()

# Rebuild and restart dashboard container
print("Rebuilding and restarting dashboard container...")
cmd = 'cd /root/Channels-grapping && docker compose build dashboard && docker compose up -d dashboard'
stdin, stdout, stderr = ssh.exec_command(cmd)
print(stdout.read().decode())
print(stderr.read().decode())

ssh.close()

# Test the live API endpoint from Python
print("Testing live endpoint http://167.233.246.102:8000/api/campaigns ...")
try:
    resp = requests.get("http://167.233.246.102:8000/api/campaigns", timeout=10)
    print(f"Status Code: {resp.status_code}")
    data = resp.json()
    print(f"Success: {data.get('success')}")
    if 'campaigns' in data and data['campaigns']:
        camp = data['campaigns'][0]
        print(f"Campaign ID: {camp.get('id')}")
        print(f"Total Recipients: {camp.get('total_recipients')}")
        print(f"Sent: {camp.get('sent_count')}")
        print(f"Failed: {camp.get('failed_count')}")
        print(f"Skipped: {camp.get('skipped_count')}")
        print(f"Pending: {camp.get('pending_count')}")
    print(f"Logs count: {len(data.get('logs', []))}")
except Exception as e:
    print(f"Request error: {e}")
