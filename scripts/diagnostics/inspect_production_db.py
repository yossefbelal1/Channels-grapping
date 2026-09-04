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

def run(cmd, label):
    print(f"\n{'='*25} {label} {'='*25}")
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out:
        print(out)
    if err:
        print(f"[STDERR]: {err}")
    return out

# 1. Git status on VPS
run('cd /root/Channels-grapping && git status && git log -n 3 --oneline', "Git Status on VPS")

# 2. Database inspection: campaigns
run('docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "SELECT id, status, created_at, SUBSTRING(message_text, 1, 60) as msg_preview FROM campaigns ORDER BY created_at DESC LIMIT 5;"', "Campaigns Table")

# 3. Database inspection: campaign_logs status breakdown
run('docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "SELECT campaign_id, status, count(*) FROM campaign_logs GROUP BY campaign_id, status ORDER BY count DESC;"', "Campaign Logs Breakdown")

# 4. Database inspection: columns in leads and campaign_logs
run('docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = \'campaign_logs\' AND column_name IN (\'priority\', \'priority_score\', \'delivery_id\', \'risk_level\', \'commercial_fit_score\');"', "Campaign Logs Columns")

run('docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = \'leads\' AND column_name IN (\'outreach_priority\', \'outreach_priority_score\', \'commercial_fit_score\', \'business_model_score\');"', "Leads Columns")

# 5. Leads overview
run('docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "SELECT count(*) as total_leads, count(CASE WHEN contact_username IS NOT NULL AND contact_username != \'\' THEN 1 END) as with_contact, count(CASE WHEN status = \'new\' THEN 1 END) as new_leads FROM leads;"', "Leads Overview")

# 6. Current priority distribution in leads
run('docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "SELECT COALESCE(outreach_priority, \'NULL\') as priority, count(*) FROM leads GROUP BY outreach_priority ORDER BY count DESC;"', "Leads Priority Distribution")

# 7. Skipped error messages breakdown
run('docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "SELECT error_message, count(*) FROM campaign_logs WHERE status = \'skipped\' GROUP BY error_message ORDER BY count DESC LIMIT 10;"', "Skipped Messages Breakdown")

# 8. Reset database error skips back to pending
run('docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "UPDATE campaign_logs SET status = \'pending\', error_message = NULL, eligibility = NULL WHERE status = \'skipped\' AND error_message = \'Not eligible: Database error\';"', "Reset DB Error Skips")

# 10. Dry run decisions inspection
run('docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "SELECT count(*) as dry_run_count FROM campaign_logs WHERE error_message = \'DRY_RUN: Message not sent\';"', "Dry Run Decisions Count")

# 11. Breakdown of P0-P4 in campaign_logs
run('docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "SELECT priority, status, error_message, count(*) FROM campaign_logs GROUP BY priority, status, error_message ORDER BY priority ASC, count DESC LIMIT 25;"', "Priority x Status Breakdown")

run('docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "SELECT cl.id, l.channel_username, l.contact_username, cl.priority, cl.priority_score, cl.status, cl.error_message FROM campaign_logs cl JOIN leads l ON cl.lead_id = l.id WHERE cl.priority = \'P0\' LIMIT 20;"', "P0 Leads in Campaign Logs")

ssh.close()
