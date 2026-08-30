import paramiko
import sys
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path)

print("=== 1. Pulling latest code on remote server ===")
stdin, stdout, stderr = ssh.exec_command('cd /root/Channels-grapping && git pull origin main')
print(stdout.read().decode())
print(stderr.read().decode())

print("=== 2. Cleaning and recovering campaign_logs in database ===")
sql_cleanup = """
-- 1. Recover valid contacts that were incorrectly marked failed
UPDATE campaign_logs cl
SET status = 'pending', error_message = NULL, sent_at = NULL
FROM leads l
WHERE cl.lead_id = l.id
  AND cl.status = 'failed'
  AND l.contact_username IS NOT NULL
  AND l.contact_username != ''
  AND LOWER(l.contact_username) NOT LIKE '%bot'
  AND LOWER(l.contact_username) NOT IN ('addlist', 'everyone', 'share', 'joinchat', 'setlanguage', 'proxy', 'socks', 'c', 's', 'm', 'i', '4030');

-- 2. Categorize failed logs with no contact username as skipped
UPDATE campaign_logs cl
SET status = 'skipped', error_message = 'No contact username'
FROM leads l
WHERE cl.lead_id = l.id
  AND cl.status = 'failed'
  AND (l.contact_username IS NULL OR l.contact_username = '');

-- 3. Categorize failed logs with bots or junk words as skipped
UPDATE campaign_logs cl
SET status = 'skipped', error_message = 'Invalid contact: bot or system keyword'
FROM leads l
WHERE cl.lead_id = l.id
  AND cl.status = 'failed'
  AND (LOWER(l.contact_username) LIKE '%bot' OR LOWER(l.contact_username) IN ('addlist', 'everyone', 'share', 'joinchat', 'setlanguage', 'proxy', 'socks', 'c', 's', 'm', 'i', '4030'));
"""

cmd_sql = f'docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "{sql_cleanup}"'
stdin, stdout, stderr = ssh.exec_command(cmd_sql)
print(stdout.read().decode())

print("=== 3. Clearing Redis rate limit and cooldown keys ===")
cmd_redis = 'docker exec leadhunter_redis redis-cli del "health:user_session:rate_limited_until" "health:user_session:dm_rate_limited_until" "campaign_sent_today:2026-08-30"'
stdin, stdout, stderr = ssh.exec_command(cmd_redis)
print(stdout.read().decode())

print("=== 4. Rebuilding & Restarting containers ===")
cmd_restart = 'cd /root/Channels-grapping && docker compose build validator dashboard && docker compose up -d validator dashboard'
stdin, stdout, stderr = ssh.exec_command(cmd_restart)
print(stdout.read().decode())
print(stderr.read().decode())

print("=== 5. Checking updated status breakdown ===")
cmd_check = 'docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "SELECT status, count(*) FROM campaign_logs GROUP BY status;"'
stdin, stdout, stderr = ssh.exec_command(cmd_check)
print(stdout.read().decode())

ssh.close()
