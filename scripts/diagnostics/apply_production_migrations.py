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
ssh.connect('167.233.246.102', username='root', key_filename=key_path, timeout=10)

sftp = ssh.open_sftp()
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

migration_files = [
    'migrate_channel_edges.sql',
    'migrate_v6_channel_intelligence.sql',
    'migrate_v7_production_hardening.sql',
    'migrate_v8_outreach_intelligence.sql',
    'migrate_outreach_engine.sql'
]

print("=== Uploading Migration Files to VPS ===")
for mig in migration_files:
    local_path = os.path.join(project_root, mig)
    remote_path = f"/root/Channels-grapping/{mig}"
    if os.path.exists(local_path):
        sftp.put(local_path, remote_path)
        print(f"Uploaded: {mig} -> {remote_path}")
    else:
        print(f"WARNING: Local file {local_path} not found!")

sftp.close()

print("\n=== Applying Migrations via Docker Postgres ===")
for mig in migration_files:
    cmd = f"docker exec -i leadhunter_postgres psql -U postgres -d leadhunter_db < /root/Channels-grapping/{mig}"
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    print(f"\n--- {mig} ---")
    if out:
        lines = out.splitlines()
        print(f"Output ({len(lines)} lines): {lines[0]} ... {lines[-1]}")
    if err:
        print(f"Stderr: {err}")

# Verify columns after migrations
check_cmd = """docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "
SELECT table_name, column_name, data_type 
FROM information_schema.columns 
WHERE table_name IN ('leads', 'campaign_logs') 
  AND column_name IN ('outreach_priority', 'outreach_priority_score', 'commercial_fit_score', 'business_model_score', 'likely_services', 'priority', 'priority_score', 'delivery_id', 'risk_level', 'risk_score')
ORDER BY table_name, column_name;
" """
stdin, stdout, stderr = ssh.exec_command(check_cmd)
print("\n=== Verified Columns in Production DB ===")
print(stdout.read().decode())

ssh.close()
