import psycopg2
import os

conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", 5432)),
    dbname=os.getenv("DB_NAME", "leadhunter"),
    user=os.getenv("DB_USER", "leadhunter"),
    password=os.getenv("DB_PASSWORD", "leadhunter"),
)
cur = conn.cursor()
cur.execute("UPDATE campaign_logs SET followup_status = NULL, followup_error_message = NULL WHERE followup_status = 'failed';")
conn.commit()
print("Reset failed followups:", cur.rowcount)
conn.close()
