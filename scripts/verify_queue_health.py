import sys
import subprocess

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

REMOTE_KEY = r"C:\Users\NV LAP\Downloads\telegram-saas-key.pem"
REMOTE_HOST = "167.233.246.102"
REMOTE_USER = "root"

def query(sql):
    cmd = [
        "ssh", "-i", REMOTE_KEY,
        "-o", "StrictHostKeyChecking=no",
        f"{REMOTE_USER}@{REMOTE_HOST}",
        f"""docker exec leadhunter_postgres psql -U postgres -d leadhunter_db -c "{sql}" """
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return res.stdout

print("=== 1. Leads Table Quality Metrics ===")
print(query("""
    SELECT 
        COUNT(*) FILTER (WHERE outreach_priority = 'P0') as total_p0_leads,
        COUNT(*) FILTER (WHERE outreach_priority = 'P0' AND (forex_intent_score = 0 OR forex_intent_score IS NULL)) as p0_zero_forex,
        COUNT(*) FILTER (WHERE outreach_priority = 'P0' AND status = 'rejected') as p0_rejected
    FROM leads;
"""))

print("=== 2. Active Campaign Queue Purity ===")
print(query("""
    SELECT 
        COUNT(*) as total_active_in_queue,
        COUNT(*) FILTER (WHERE l.forex_intent_score = 0 OR l.forex_intent_score IS NULL) as zero_forex_in_queue,
        COUNT(*) FILTER (WHERE l.status = 'rejected') as rejected_in_queue,
        COUNT(*) FILTER (WHERE l.contact_username IS NULL OR l.contact_username = '') as no_contact_in_queue
    FROM campaign_logs cl
    JOIN leads l ON cl.lead_id = l.id
    WHERE cl.status IN ('approved', 'pending');
"""))

print("=== 3. Channel @whyyyvv Status Check ===")
print(query("""
    SELECT l.channel_username, l.outreach_priority, l.outreach_priority_score, cl.status as campaign_status, cl.error_message
    FROM leads l
    LEFT JOIN campaign_logs cl ON l.id = cl.lead_id
    WHERE l.channel_username = 'whyyyvv';
"""))
