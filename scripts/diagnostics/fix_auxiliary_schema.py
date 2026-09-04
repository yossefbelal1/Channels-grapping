import paramiko
import sys

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key_path = r'C:\Users\NV LAP\Downloads\telegram-saas-key.pem'
ssh.connect('167.233.246.102', username='root', key_filename=key_path, timeout=10)

sql = """
ALTER TABLE leads ADD COLUMN IF NOT EXISTS next_crawl_at TIMESTAMP;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS activity_class VARCHAR(20) DEFAULT 'WARM';
CREATE TABLE IF NOT EXISTS channel_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id UUID REFERENCES leads(id),
    member_count INT,
    post_count INT,
    posts_24h INT,
    posts_7d INT,
    posts_30d INT,
    lead_score INT,
    forex_score INT,
    activity_score INT,
    scores_dict JSONB,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_leads_next_crawl
    ON leads(next_crawl_at, activity_class, lead_score DESC)
    WHERE next_crawl_at IS NOT NULL;
"""

cmd = f'docker exec -i leadhunter_postgres psql -U postgres -d leadhunter_db << "EOF"\n{sql}\nEOF'
stdin, stdout, stderr = ssh.exec_command(cmd)
print("Stdout:", stdout.read().decode())
print("Stderr:", stderr.read().decode())
ssh.close()
