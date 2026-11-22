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

print("=== 1. FULL LEADS TABLE CONTACTS ANALYSIS ===")
cur.execute("""
    SELECT 
        COUNT(id) as total_leads,
        COUNT(CASE WHEN contact_username IS NOT NULL AND contact_username != '' THEN 1 END) as leads_with_contact,
        COUNT(DISTINCT LOWER(TRIM(LEADING '@' FROM TRIM(contact_username)))) as unique_contacts
    FROM leads;
""")
print(dict(cur.fetchone()))

print("\n=== 2. CAMPAIGN LOGS vs SENT CONTACTS IN LEADS ===")
# How many unique contacts in leads have ALREADY been sent a message?
cur.execute("""
    SELECT COUNT(DISTINCT LOWER(TRIM(LEADING '@' FROM TRIM(l.contact_username)))) as sent_unique_contacts
    FROM campaign_logs cl
    JOIN leads l ON cl.lead_id = l.id
    WHERE cl.status = 'sent' AND l.contact_username IS NOT NULL AND l.contact_username != '';
""")
print(dict(cur.fetchone()))

# Clean up any remaining duplicate in campaign_logs (like @ooeaaoo)
cur.execute("""
    WITH ranked_pending AS (
        SELECT cl.id,
               LOWER(TRIM(LEADING '@' FROM TRIM(l.contact_username))) as clean_contact,
               ROW_NUMBER() OVER (
                   PARTITION BY LOWER(TRIM(LEADING '@' FROM TRIM(l.contact_username)))
                   ORDER BY 
                       CASE cl.status WHEN 'approved' THEN 1 WHEN 'processing' THEN 2 ELSE 3 END,
                       CASE COALESCE(l.outreach_priority, cl.priority, 'P3')
                           WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END,
                       COALESCE(l.outreach_priority_score, cl.priority_score, 0) DESC,
                       cl.id ASC
               ) as rn
        FROM campaign_logs cl
        JOIN leads l ON cl.lead_id = l.id
        WHERE cl.status IN ('approved', 'pending', 'pending_review', 'processing')
          AND l.contact_username IS NOT NULL
          AND l.contact_username != ''
    )
    UPDATE campaign_logs
    SET status = 'skipped',
        error_message = 'Deduplicated: Contact already in queue under another channel',
        sent_at = NOW()
    WHERE id IN (SELECT id FROM ranked_pending WHERE rn > 1);
""")
conn.commit()
print("Cleaned up remaining cross-status duplicates:", cur.rowcount)

# Re-check duplicates among ALL active/pending/approved/processing
cur.execute("""
    SELECT 
        LOWER(TRIM(LEADING '@' FROM TRIM(l.contact_username))) as contact,
        count(cl.id) as cnt
    FROM campaign_logs cl
    JOIN leads l ON cl.lead_id = l.id
    WHERE cl.status IN ('approved', 'pending', 'pending_review', 'processing')
      AND l.contact_username IS NOT NULL AND l.contact_username != ''
    GROUP BY LOWER(TRIM(LEADING '@' FROM TRIM(l.contact_username)))
    HAVING count(cl.id) > 1;
""")
active_dupes = cur.fetchall()
print(f"Remaining active duplicate contacts in queue: {len(active_dupes)}")

# Campaign Summary
cur.execute("""
    SELECT status, count(id) as count FROM campaign_logs GROUP BY status ORDER BY count DESC;
""")
print("\n=== FINAL CAMPAIGN LOGS STATUS BREAKDOWN ===")
for r in cur.fetchall():
    print(f"  {r['status']}: {r['count']}")

cur.close()
conn.close()
