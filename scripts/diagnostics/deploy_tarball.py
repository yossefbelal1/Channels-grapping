import tarfile
import paramiko
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
tar_path = os.path.join(project_root, 'deploy_outreach.tar.gz')

print("1. Creating local deploy archive...")
with tarfile.open(tar_path, "w:gz") as tar:
    # Add app directory
    tar.add(os.path.join(project_root, "app"), arcname="app")
    # Add root files
    for fname in ["validator.py", "campaign_worker.py", "dashboard.py"]:
        fpath = os.path.join(project_root, fname)
        if os.path.exists(fpath):
            tar.add(fpath, arcname=fname)
    # Add preflight and reconciliation scripts
    for sname in ["outreach_preflight.py", "reconcile_production_leads.py"]:
        spath = os.path.join(project_root, "scripts", sname)
        if os.path.exists(spath):
            tar.add(spath, arcname=f"scripts/{sname}")

size_kb = os.path.getsize(tar_path) / 1024.0
print(f"   Archive created: {tar_path} ({size_kb:.1f} KB)")

print("2. Uploading archive to VPS...")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path, timeout=10)

sftp = ssh.open_sftp()
sftp.put(tar_path, "/root/Channels-grapping/deploy_outreach.tar.gz")
sftp.close()
print("   Upload complete!")

print("3. Extracting archive on VPS...")
cmd = "cd /root/Channels-grapping && tar -xzf deploy_outreach.tar.gz && rm deploy_outreach.tar.gz"
stdin, stdout, stderr = ssh.exec_command(cmd)
print("   Extract stdout:", stdout.read().decode())
print("   Extract stderr:", stderr.read().decode())

print("4. Verifying Python import on VPS...")
cmd = "cd /root/Channels-grapping && python3 -c 'from app.outreach.priority_engine import OutreachPriorityEngine; print(\"IMPORT SUCCESSFUL ON VPS!\")'"
stdin, stdout, stderr = ssh.exec_command(cmd)
print("   " + stdout.read().decode().strip())
err = stderr.read().decode().strip()
if err:
    print("   [STDERR]:", err)

ssh.close()

# Cleanup local tarball
if os.path.exists(tar_path):
    os.remove(tar_path)
print("=== Deployment finished ===")
