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

print("=== 1. CAMPAIGN LOGS STATUS BREAKDOWN ===")
cur.execute("SELECT status, count(id) as count FROM campaign_logs GROUP BY status ORDER BY count DESC;")
for r in cur.fetchall():
    print(f"  {r['status']}: {r['count']}")

print("\n=== 2. SENT MESSAGES DEDUPLICATION CHECK ===")
cur.execute("""
    SELECT 
        LOWER(TRIM(LEADING '@' FROM l.contact_username)) as clean_contact,
        count(cl.id) as sent_count,
        array_agg(cl.id::text) as log_ids,
        array_agg(l.channel_username) as channels
    FROM campaign_logs cl
    JOIN leads l ON cl.lead_id = l.id
    WHERE cl.status = 'sent' 
      AND l.contact_username IS NOT NULL 
      AND l.contact_username != ''
    GROUP BY LOWER(TRIM(LEADING '@' FROM l.contact_username))
    HAVING count(cl.id) > 1
    ORDER BY sent_count DESC;
""")
sent_dupes = cur.fetchall()
print(f"Total contacts sent to more than once: {len(sent_dupes)}")
for r in sent_dupes[:15]:
    print(f"  Contact @{r['clean_contact']}: Sent {r['sent_count']} times! Channels: {r['channels']}")

print("\n=== 3. PENDING / APPROVED DUPLICATE CONTACTS (ABOUT TO BE SENT) ===")
# 3a. In pending/approved/pending_review who were ALREADY sent a message previously
cur.execute("""
    SELECT 
        LOWER(TRIM(LEADING '@' FROM l.contact_username)) as clean_contact,
        cl.id as log_id,
        cl.status as log_status,
        l.channel_username
    FROM campaign_logs cl
    JOIN leads l ON cl.lead_id = l.id
    WHERE cl.status IN ('approved', 'pending', 'pending_review')
      AND LOWER(TRIM(LEADING '@' FROM l.contact_username)) IN (
          SELECT LOWER(TRIM(LEADING '@' FROM l2.contact_username))
          FROM campaign_logs cl2
          JOIN leads l2 ON cl2.lead_id = l2.id
          WHERE cl2.status = 'sent'
            AND l2.contact_username IS NOT NULL
            AND l2.contact_username != ''
      );
""")
pending_already_sent = cur.fetchall()
print(f"Pending/Approved logs whose contact was ALREADY messaged (MUST BE SKIPPED): {len(pending_already_sent)}")
for r in pending_already_sent[:15]:
    print(f"  Log {r['log_id']} (Status: {r['log_status']}) -> Contact @{r['clean_contact']} (Channel: @{r['channel_username']})")

# 3b. Duplicate contacts within approved/pending queue itself
cur.execute("""
    SELECT 
        LOWER(TRIM(LEADING '@' FROM l.contact_username)) as clean_contact,
        count(cl.id) as queue_count,
        array_agg(cl.id::text) as log_ids,
        array_agg(cl.status) as statuses,
        array_agg(l.channel_username) as channels
    FROM campaign_logs cl
    JOIN leads l ON cl.lead_id = l.id
    WHERE cl.status IN ('approved', 'pending', 'pending_review')
      AND l.contact_username IS NOT NULL 
      AND l.contact_username != ''
    GROUP BY LOWER(TRIM(LEADING '@' FROM l.contact_username))
    HAVING count(cl.id) > 1
    ORDER BY queue_count DESC;
""")
queue_dupes = cur.fetchall()
print(f"\nContacts duplicated multiple times inside approved/pending queue: {len(queue_dupes)}")
for r in queue_dupes[:15]:
    print(f"  Contact @{r['clean_contact']}: in queue {r['queue_count']} times! Channels: {r['channels']}")

cur.close()
conn.close()
