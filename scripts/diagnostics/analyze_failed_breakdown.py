import paramiko
import sys
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path)

# 1. Inspect how many failed logs have valid contacts vs no contact vs bot
query_analysis = '''
SELECT 
    COUNT(*) as total_failed,
    COUNT(*) FILTER (WHERE l.contact_username IS NOT NULL AND l.contact_username != '' AND LOWER(l.contact_username) NOT LIKE '%bot' AND LOWER(l.contact_username) NOT IN ('addlist', 'everyone', 'share', 'joinchat', 'setlanguage', 'proxy', 'socks', 'c', 's', 'm', 'i', '4030')) as recoverable_valid_contacts,
    COUNT(*) FILTER (WHERE l.contact_username IS NULL OR l.contact_username = '') as no_contacts,
    COUNT(*) FILTER (WHERE l.contact_username IS NOT NULL AND (LOWER(l.contact_username) LIKE '%bot' OR LOWER(l.contact_username) IN ('addlist', 'everyone', 'share', 'joinchat', 'setlanguage', 'proxy', 'socks', 'c', 's', 'm', 'i', '4030'))) as junk_or_bots
FROM campaign_logs cl
JOIN leads l ON cl.lead_id = l.id
WHERE cl.status = 'failed';
'''

cmd = f'docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "{query_analysis}"'
stdin, stdout, stderr = ssh.exec_command(cmd)
print("=== Failed Logs Categorization ===")
print(stdout.read().decode())

ssh.close()
