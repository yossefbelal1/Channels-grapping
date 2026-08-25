"""Print no-contact channels as CSV to stdout"""
import psycopg2, os, csv, sys

conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", 5432)),
    dbname=os.getenv("DB_NAME", "leadhunter"),
    user=os.getenv("DB_USER", "leadhunter"),
    password=os.getenv("DB_PASSWORD", "leadhunter")
)
cur = conn.cursor()
cur.execute("SELECT id FROM campaigns WHERE id::text LIKE %s LIMIT 1", ("30d91eeb%",))
cid = cur.fetchone()[0]

cur.execute("""
    SELECT l.channel_username, l.member_count, l.lead_score, l.tier
    FROM campaign_logs cl
    JOIN leads l ON l.id = cl.lead_id
    WHERE cl.campaign_id = %s
      AND cl.status IN ('failed', 'FAILED', 'error', 'ERROR')
      AND cl.error_message ILIKE '%%No owner or admin contact%%'
    ORDER BY l.member_count DESC NULLS LAST
""", (cid,))

rows = cur.fetchall()
w = csv.writer(sys.stdout)
w.writerow(['channel_username', 'telegram_link', 'member_count', 'lead_score', 'tier'])
for r in rows:
    uname = r[0] or ''
    w.writerow([uname, f"https://t.me/{uname}" if uname else '', r[1] or 0, r[2] or 0, r[3] or ''])

sys.stderr.write(f"Total: {len(rows)} channels\n")
conn.close()
