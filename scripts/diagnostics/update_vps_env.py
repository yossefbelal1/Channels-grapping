import paramiko
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

env_additions = """
# ── Outreach Engine Configuration ─────────────────────────────────────────────
OUTREACH_ENABLED=true
OUTREACH_DRY_RUN=true
OUTREACH_CANARY_SIZE=5
OUTREACH_MAX_RETRIES=3
OUTREACH_LEAD_COOLDOWN_DAYS=30
OUTREACH_RECONCILIATION_INTERVAL=300
"""

cmd = f"""
grep -qF "OUTREACH_ENABLED" /root/Channels-grapping/.env || cat << 'EOF' >> /root/Channels-grapping/.env
{env_additions}
EOF
tail -n 15 /root/Channels-grapping/.env
"""

stdin, stdout, stderr = ssh.exec_command(cmd)
print("=== Updated .env on VPS ===")
print(stdout.read().decode())
print("Stderr:", stderr.read().decode())

ssh.close()
