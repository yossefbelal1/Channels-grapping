import paramiko
import sys

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path, timeout=10)

def run(cmd, label):
    print(f"\n{'='*20} {label} {'='*20}")
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out:
        print(out)
    if err:
        print(f"[STDERR]: {err}")
    return out

run("""docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "
SELECT count(*) as posts_count FROM channel_posts;
" """, "Channel Posts Count")

run("""docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "
SELECT 
    count(CASE WHEN description IS NOT NULL AND length(description) > 5 THEN 1 END) as with_desc,
    count(CASE WHEN scoring_evidence IS NOT NULL THEN 1 END) as with_evidence,
    count(CASE WHEN forex_score > 0 THEN 1 END) as with_forex_score,
    count(CASE WHEN lead_score >= 50 THEN 1 END) as high_lead_score
FROM leads;
" """, "Leads Content Availability")

run("""docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "
SELECT l.channel_username, l.member_count, l.contact_username, l.forex_score, l.lead_score, SUBSTRING(l.description, 1, 80) as desc_preview
FROM campaign_logs cl
JOIN leads l ON cl.lead_id = l.id
WHERE cl.status = 'pending'
LIMIT 5;
" """, "Sample Pending Leads")

ssh.close()
