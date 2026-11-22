import os
import psycopg2
from psycopg2.extras import RealDictCursor

db_host = os.getenv("DB_HOST", os.getenv("POSTGRES_HOST", "postgres"))
db_port = int(os.getenv("DB_PORT", os.getenv("POSTGRES_PORT", 5432)))
db_name = os.getenv("DB_NAME", os.getenv("POSTGRES_DB", "leadhunter_db"))
db_user = os.getenv("DB_USER", os.getenv("POSTGRES_USER", "postgres"))
db_pass = os.getenv("DB_PASSWORD", os.getenv("POSTGRES_PASSWORD", ""))

conn = psycopg2.connect(host=db_host, port=db_port, dbname=db_name, user=db_user, password=db_pass)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=== CAMPAIGN RECIPIENTS BREAKDOWN ===")
cur.execute("""
    SELECT 
        c.id as campaign_id,
        COUNT(cl.id) as total_recipients,
        COUNT(CASE WHEN cl.status = 'sent' THEN 1 END) as sent_count,
        COUNT(CASE WHEN cl.status = 'failed' THEN 1 END) as failed_count,
        COUNT(CASE WHEN cl.status = 'skipped' THEN 1 END) as skipped_count,
        COUNT(CASE WHEN cl.status = 'approved' THEN 1 END) as approved_count,
        COUNT(CASE WHEN cl.status IN ('pending', 'pending_review') THEN 1 END) as pending_review_count,
        COUNT(CASE WHEN cl.status IN ('approved', 'pending', 'pending_review') THEN 1 END) as total_pending,
        COUNT(CASE WHEN cl.status = 'approved' AND cl.priority = 'P0' THEN 1 END) as approved_p0,
        COUNT(CASE WHEN cl.status = 'approved' AND cl.priority = 'P1' THEN 1 END) as approved_p1,
        COUNT(CASE WHEN cl.status = 'approved' AND cl.priority = 'P2' THEN 1 END) as approved_p2,
        COUNT(CASE WHEN cl.status = 'approved' AND cl.priority = 'P3' THEN 1 END) as approved_p3
    FROM campaigns c
    LEFT JOIN campaign_logs cl ON c.id = cl.campaign_id
    GROUP BY c.id;
""")
for r in cur.fetchall():
    print(dict(r))

cur.close()
conn.close()
