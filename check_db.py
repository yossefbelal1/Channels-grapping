import psycopg2

try:
    conn = psycopg2.connect("postgresql://postgres:leadhunter_pass@postgres/leadhunter_db")
    cur = conn.cursor()
    
    cur.execute("""
        SELECT channel_username, lead_score, status, last_scan, last_activity 
        FROM leads 
        WHERE status != 'rejected' AND lead_score >= 10 
        ORDER BY last_activity DESC NULLS LAST
    """)
    rows = cur.fetchall()
    print("Verified leads currently visible on the dashboard:")
    for r in rows:
        print(f"Username: {r[0]} | Score: {r[1]} | Status: {r[2]} | Last Scan: {r[3]} | Last Activity: {r[4]}")
        
except Exception as e:
    print(f"Error checking database: {e}")
