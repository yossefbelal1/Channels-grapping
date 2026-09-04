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
SELECT 
    count(*) as total,
    count(CASE WHEN outreach_priority IS NOT NULL THEN 1 END) as with_outreach_priority,
    count(CASE WHEN commercial_fit_score > 0 THEN 1 END) as with_commercial_fit,
    count(CASE WHEN contact_username IS NOT NULL AND contact_username != '' THEN 1 END) as with_contact
FROM leads;
" """, "Leads Outreach Intelligence Counts")

run("""docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "
SELECT 
    status,
    count(*) as total,
    count(CASE WHEN priority IS NOT NULL THEN 1 END) as with_priority,
    count(CASE WHEN priority = 'P0' THEN 1 END) as p0_count,
    count(CASE WHEN priority = 'P1' THEN 1 END) as p1_count,
    count(CASE WHEN priority = 'P2' THEN 2 END) as p2_count,
    count(CASE WHEN priority = 'P3' THEN 3 END) as p3_count,
    count(CASE WHEN priority = 'P4' THEN 4 END) as p4_count
FROM campaign_logs
GROUP BY status;
" """, "Campaign Logs Priority Breakdown")

ssh.close()
