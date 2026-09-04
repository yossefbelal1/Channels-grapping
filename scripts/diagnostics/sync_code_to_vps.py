import paramiko
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path, timeout=10)
sftp = ssh.open_sftp()

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
remote_root = "/root/Channels-grapping"

def sftp_mkdir_p(remote_directory):
    dirs_ = []
    dir_ = remote_directory
    while len(dir_) > 1:
        dirs_.append(dir_)
        dir_, _ = os.path.split(dir_)
    if len(dir_) == 1:
        dirs_.append(dir_)
    while len(dirs_):
        d = dirs_.pop()
        try:
            sftp.stat(d)
        except Exception:
            try:
                sftp.mkdir(d)
            except Exception:
                pass

def upload_file(local, remote):
    sftp_mkdir_p(os.path.dirname(remote))
    sftp.put(local, remote)
    print(f"Uploaded: {os.path.relpath(local, project_root)} -> {remote}")

def upload_dir(local_dir, remote_dir):
    for root, dirs, files in os.walk(local_dir):
        # Skip __pycache__, .git, .pytest_cache
        if any(ignored in root for ignored in ['__pycache__', '.git', '.pytest_cache']):
            continue
        rel = os.path.relpath(root, local_dir)
        target_dir = os.path.join(remote_dir, rel).replace('\\', '/')
        sftp_mkdir_p(target_dir)
        for f in files:
            if f.endswith(('.pyc', '.tmp', '.log')):
                continue
            src = os.path.join(root, f)
            dst = os.path.join(target_dir, f).replace('\\', '/')
            upload_file(src, dst)

print("=== Uploading updated codebase to VPS ===")
# 1. Upload app/ directory
upload_dir(os.path.join(project_root, 'app'), f"{remote_root}/app")

# 2. Upload root files
for fname in ['validator.py', 'campaign_worker.py', 'dashboard.py', 'requirements.txt', 'docker-compose.yml']:
    src = os.path.join(project_root, fname)
    if os.path.exists(src):
        upload_file(src, f"{remote_root}/{fname}")

# 3. Upload scripts/
upload_dir(os.path.join(project_root, 'scripts'), f"{remote_root}/scripts")

sftp.close()
print("=== Code Upload Complete ===")

# Verify that python can import app.outreach on the VPS
stdin, stdout, stderr = ssh.exec_command('cd /root/Channels-grapping && python3 -c "from app.outreach.priority_engine import OutreachPriorityEngine; print(\'IMPORT SUCCESS!\')"')
print("Import verification on VPS:")
print(stdout.read().decode())
print("Stderr:", stderr.read().decode())

ssh.close()
