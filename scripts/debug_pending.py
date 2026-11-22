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

print("=== 1. PENDING ROWS BREAKDOWN ===")
cur.execute("""
    SELECT 
        COUNT(cl.id) as total_pending,
        COUNT(DISTINCT LOWER(TRIM(LEADING '@' FROM TRIM(l.contact_username)))) as distinct_contacts,
        COUNT(CASE WHEN l.contact_username IS NULL OR l.contact_username = '' THEN 1 END) as empty_contacts,
        COUNT(CASE WHEN cl.status = 'approved' THEN 1 END) as approved_count,
        COUNT(CASE WHEN cl.status = 'pending_review' THEN 1 END) as pending_review_count,
        COUNT(CASE WHEN cl.status = 'pending' THEN 1 END) as pending_legacy_count
    FROM campaign_logs cl
    JOIN leads l ON cl.lead_id = l.id
    WHERE cl.status IN ('pending', 'pending_review', 'approved');
""")
row = cur.fetchone()
print(dict(row))

print("\n=== 2. ARE THERE ANY DUPLICATES AMONG THE 4,209 ROWS? ===")
cur.execute("""
    SELECT 
        LOWER(TRIM(LEADING '@' FROM TRIM(l.contact_username))) as contact,
        count(cl.id) as cnt,
        array_agg(cl.id::text) as log_ids,
        array_agg(cl.status) as statuses,
        array_agg(l.channel_username) as channels
    FROM campaign_logs cl
    JOIN leads l ON cl.lead_id = l.id
    WHERE cl.status IN ('pending', 'pending_review', 'approved')
      AND l.contact_username IS NOT NULL AND l.contact_username != ''
    GROUP BY LOWER(TRIM(LEADING '@' FROM TRIM(l.contact_username)))
    HAVING count(cl.id) > 1
    ORDER BY cnt DESC;
""")
dupes = cur.fetchall()
print(f"Total contacts that have duplicate rows in pending: {len(dupes)}")
for d in dupes[:15]:
    print(f"  Contact @{d['contact']}: {d['cnt']} rows | Statuses: {d['statuses']} | Channels: {d['channels']}")

print("\n=== 3. HAVE ANY OF THE 4,209 CONTACTS ALREADY BEEN SENT A MESSAGE? ===")
cur.execute("""
    SELECT 
        LOWER(TRIM(LEADING '@' FROM TRIM(l.contact_username))) as contact,
        cl.id as pending_log_id,
        cl.status as pending_status,
        l.channel_username as pending_channel
    FROM campaign_logs cl
    JOIN leads l ON cl.lead_id = l.id
    WHERE cl.status IN ('pending', 'pending_review', 'approved')
      AND l.contact_username IS NOT NULL AND l.contact_username != ''
      AND LOWER(TRIM(LEADING '@' FROM TRIM(l.contact_username))) IN (
          SELECT DISTINCT LOWER(TRIM(LEADING '@' FROM TRIM(l_sent.contact_username)))
          FROM campaign_logs cl_sent
          JOIN leads l_sent ON cl_sent.lead_id = l_sent.id
          WHERE cl_sent.status = 'sent' AND l_sent.contact_username IS NOT NULL AND l_sent.contact_username != ''
      );
""")
already_sent = cur.fetchall()
print(f"Pending rows whose contact was already sent: {len(already_sent)}")
for a in already_sent[:10]:
    print(f"  @{a['contact']} (Pending log: {a['pending_log_id']}, channel: @{a['pending_channel']})")

print("\n=== 4. WHAT ARE THE LATEST 10 ATTEMPTS SHOWN IN THE DASHBOARD TABLE? ===")
cur.execute("""
    SELECT cl.id, cl.status, cl.error_message, cl.sent_at,
           l.channel_username, l.contact_username,
           COALESCE(l.outreach_priority, cl.priority, 'P3') as priority,
           COALESCE(l.outreach_priority_score, cl.priority_score, 25) as priority_score
    FROM campaign_logs cl
    JOIN campaigns c ON cl.campaign_id = c.id
    JOIN leads l ON cl.lead_id = l.id
    ORDER BY 
        CASE cl.status
            WHEN 'processing' THEN 0
            WHEN 'approved' THEN 1
            WHEN 'pending' THEN 2
            WHEN 'pending_review' THEN 3
            ELSE 4
        END ASC,
        CASE COALESCE(l.outreach_priority, cl.priority, 'P3')
            WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3
        END ASC,
        COALESCE(l.outreach_priority_score, cl.priority_score, 25) DESC
    LIMIT 10;
""")
for r in cur.fetchall():
    print(f"  Log: {r['id']} | Status: {r['status']} | Priority: {r['priority']} ({r['priority_score']}) | Channel: @{r['channel_username']} | Contact: @{r['contact_username']}")

print("\n=== 5. CHECK QUEEN_EL_GOLD AND SUPPOR_T7 ===")
cur.execute("""
    SELECT cl.id, cl.status, cl.error_message, cl.sent_at, l.contact_username, l.channel_username, cl.priority, cl.priority_score
    FROM campaign_logs cl
    JOIN leads l ON cl.lead_id = l.id
    WHERE l.channel_username ILIKE '%queen_el_gold%' OR l.contact_username ILIKE '%SUPPOR_T7%';
""")
for r in cur.fetchall():
    print(dict(r))

cur.close()
conn.close()
