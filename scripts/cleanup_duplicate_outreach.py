import os
import psycopg2
from psycopg2.extras import RealDictCursor
import redis

db_host = os.getenv("DB_HOST", os.getenv("POSTGRES_HOST", "postgres"))
db_port = int(os.getenv("DB_PORT", os.getenv("POSTGRES_PORT", 5432)))
db_name = os.getenv("DB_NAME", os.getenv("POSTGRES_DB", "leadhunter_db"))
db_user = os.getenv("DB_USER", os.getenv("POSTGRES_USER", "postgres"))
db_pass = os.getenv("DB_PASSWORD", os.getenv("POSTGRES_PASSWORD", ""))

conn = psycopg2.connect(host=db_host, port=db_port, dbname=db_name, user=db_user, password=db_pass)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("--- STEP 1: Skipping pending/approved leads whose contact was already sent a message ---")
cur.execute("""
    UPDATE campaign_logs cl
    SET status = 'skipped',
        error_message = 'Deduplicated: Contact already messaged previously',
        sent_at = NOW()
    FROM leads l
    WHERE cl.lead_id = l.id
      AND cl.status IN ('approved', 'pending', 'pending_review', 'processing')
      AND l.contact_username IS NOT NULL
      AND l.contact_username != ''
      AND LOWER(TRIM(LEADING '@' FROM TRIM(l.contact_username))) IN (
          SELECT DISTINCT LOWER(TRIM(LEADING '@' FROM TRIM(l_sent.contact_username)))
          FROM campaign_logs cl_sent
          JOIN leads l_sent ON cl_sent.lead_id = l_sent.id
          WHERE cl_sent.status = 'sent'
            AND l_sent.contact_username IS NOT NULL
            AND l_sent.contact_username != ''
      );
""")
conn.commit()
skipped_already_sent = cur.rowcount
print(f"Skipped {skipped_already_sent} logs for contacts already messaged.")

print("--- STEP 2: Deduplicating multiple channels for the same contact in approved/pending queue ---")
cur.execute("""
    WITH ranked_logs AS (
        SELECT cl.id,
               LOWER(TRIM(LEADING '@' FROM TRIM(l.contact_username))) as clean_contact,
               ROW_NUMBER() OVER (
                   PARTITION BY LOWER(TRIM(LEADING '@' FROM TRIM(l.contact_username)))
                   ORDER BY 
                       CASE cl.status WHEN 'approved' THEN 1 ELSE 2 END,
                       CASE COALESCE(l.outreach_priority, cl.priority, 'P3')
                           WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END,
                       COALESCE(l.outreach_priority_score, cl.priority_score, 0) DESC,
                       cl.id ASC
               ) as rn
        FROM campaign_logs cl
        JOIN leads l ON cl.lead_id = l.id
        WHERE cl.status IN ('approved', 'pending', 'pending_review')
          AND l.contact_username IS NOT NULL
          AND l.contact_username != ''
    )
    UPDATE campaign_logs
    SET status = 'skipped',
        error_message = 'Deduplicated: Multiple channels share same owner in queue',
        sent_at = NOW()
    WHERE id IN (SELECT id FROM ranked_logs WHERE rn > 1);
""")
conn.commit()
skipped_queue_dupes = cur.rowcount
print(f"Skipped {skipped_queue_dupes} duplicate logs in queue.")

# 3. Warm up Redis set 'outreach:messaged_contacts'
redis_host = os.getenv("REDIS_HOST", "redis")
redis_port = int(os.getenv("REDIS_PORT", 6379))
r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
try:
    cur.execute("""
        SELECT DISTINCT LOWER(TRIM(LEADING '@' FROM TRIM(l.contact_username))) as c
        FROM campaign_logs cl
        JOIN leads l ON cl.lead_id = l.id
        WHERE cl.status = 'sent' AND l.contact_username IS NOT NULL AND l.contact_username != '';
    """)
    rows = cur.fetchall()
    contacts = [row['c'] for row in rows if row.get('c')]
    if contacts:
        for i in range(0, len(contacts), 500):
            r.sadd("outreach:messaged_contacts", *contacts[i:i+500])
    print(f"Warmed up Redis 'outreach:messaged_contacts' with {len(contacts)} contacts.")
except Exception as e:
    print(f"Redis warm-up error: {e}")

# Verification Summary
cur.execute("SELECT status, count(id) as count FROM campaign_logs GROUP BY status ORDER BY count DESC;")
print("\n=== UPDATED CAMPAIGN LOGS STATUS BREAKDOWN ===")
for row in cur.fetchall():
    print(f"  {row['status']}: {row['count']}")

cur.close()
conn.close()
