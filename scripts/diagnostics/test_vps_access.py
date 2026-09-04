import paramiko
import sys
import os

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'

connected = False
try:
    if os.path.exists(key_path):
        print(f'Attempting SSH key connection with {key_path}...')
        ssh.connect('167.233.246.102', username='root', key_filename=key_path, timeout=10)
        connected = True
        print('SSH Key Connection SUCCESS!')
except Exception as e:
    print(f'Key connection failed: {e}')

if not connected:
    try:
        print('Attempting password connection...')
        ssh.connect('167.233.246.102', username='root', password='Ae9eM3H9wppv3cxaPibU', timeout=10, look_for_keys=False, allow_agent=False)
        connected = True
        print('SSH Password Connection SUCCESS!')
    except Exception as e:
        print(f'Password connection failed: {e}')

if connected:
    stdin, stdout, stderr = ssh.exec_command('docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"')
    print('=== Running Containers ===')
    print(stdout.read().decode())

    stdin, stdout, stderr = ssh.exec_command('pwd; git status')
    print('=== Repo Status on VPS ===')
    print(stdout.read().decode())
    print(stderr.read().decode())
    ssh.close()
else:
    print('Could not connect to VPS.')
