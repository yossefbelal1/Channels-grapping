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

# 1. Copy the updated code into the container or mount it
# Let's check container files:
cmd1 = 'docker exec worker_validator ls -la /app'
stdin, stdout, stderr = ssh.exec_command(cmd1)
print("=== /app in worker_validator ===")
print(stdout.read().decode())

# 2. Copy the updated app directory into the container
cmd2 = 'docker cp /root/Channels-grapping/app worker_validator:/app/ && docker cp /root/Channels-grapping/scripts worker_validator:/app/ && docker cp /root/Channels-grapping/validator.py worker_validator:/app/ && docker cp /root/Channels-grapping/campaign_worker.py worker_validator:/app/ && docker cp /root/Channels-grapping/dashboard.py worker_validator:/app/'
stdin, stdout, stderr = ssh.exec_command(cmd2)
print("=== docker cp into container ===")
print("Stderr if any:", stderr.read().decode())

# 3. Test running the reconciliation script inside the container
# Notice in container DB_HOST is 'postgres'
cmd3 = 'docker exec worker_validator python /app/scripts/reconcile_production_leads.py'
stdin, stdout, stderr = ssh.exec_command(cmd3)
print("=== Output from reconcile_production_leads.py in container ===")
print(stdout.read().decode())
print("Stderr if any:", stderr.read().decode())

ssh.close()
