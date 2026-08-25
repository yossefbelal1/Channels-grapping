import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

# Connect to database
conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", 5432)),
    database=os.getenv("DB_NAME", "leadhunter_db"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", "postgres")
)

try:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # 1. Total leads
        cur.execute("SELECT COUNT(*) FROM leads")
        total_leads = cur.fetchone()['count']
        
        # 2. Leads by status
        cur.execute("SELECT status, COUNT(*) FROM leads GROUP BY status")
        status_counts = cur.fetchall()
        
        # 3. Active Leads in dashboard (forex_intent_score >= 10 AND language = 'Arabic' AND status = 'new')
        cur.execute("""
            SELECT COUNT(*) FROM leads 
            WHERE status = 'new' 
              AND lead_score >= 10 
              AND language = 'Arabic'
        """)
        visible_leads = cur.fetchone()['count']
        
        # 4. Leads with contact_username resolved but status = 'new'
        cur.execute("""
            SELECT COUNT(*) FROM leads 
            WHERE status = 'new' 
              AND contact_username IS NOT NULL
        """)
        new_with_contact = cur.fetchone()['count']
        
        # 5. Leads in campaign queue (pending in active campaign)
        cur.execute("""
            SELECT COUNT(*) FROM campaign_logs 
            WHERE status = 'pending'
        """)
        pending_campaign = cur.fetchone()['count']

        print("==============================================")
        print("          DATABASE LEADS ANALYSIS             ")
        print("==============================================")
        print(f"Total Leads in DB                   : {total_leads}")
        print(f"Active Visible Leads on Dashboard   : {visible_leads}")
        print(f"New Leads with Resolved Contact     : {new_with_contact}")
        print(f"Pending Outreach Messages in Queue  : {pending_campaign}")
        print("----------------------------------------------")
        print("Leads by Status:")
        for row in status_counts:
            print(f"  - {row['status']}: {row['count']}")
        print("==============================================")

finally:
    conn.close()
