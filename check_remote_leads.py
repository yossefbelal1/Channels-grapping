import psycopg2

try:
    conn = psycopg2.connect("postgresql://postgres:leadhunter_pass@postgres/leadhunter_db")
    cur = conn.cursor()
    
    usernames = ['ITradly', 'alskndry']
    for username in usernames:
        cur.execute("""
            SELECT id, channel_username, description, is_group, forex_intent_score, lead_score, status, last_scan, arabic_score, region_score
            FROM leads 
            WHERE channel_username = %s
        """, (username,))
        row = cur.fetchone()
        if row:
            lead_id, u, desc, is_group, forex, score, status, last_scan, arabic_score, region_score = row
            print(f"=================================")
            print(f"@{u} details:")
            print(f"Is Group: {is_group}")
            print(f"Description: {desc[:300] if desc else 'None'}")
            print(f"Forex Intent: {forex}")
            print(f"Lead Score: {score}")
            print(f"Arabic Score: {arabic_score}")
            print(f"Region Score: {region_score}")
            print(f"Status: {status}")
            print(f"Last Scan: {last_scan}")
            
            # Fetch keyword frequencies
            cur.execute("SELECT keyword, frequency FROM channel_keywords WHERE channel_id = %s", (lead_id,))
            kw_rows = cur.fetchall()
            print(f"Keyword Frequencies: {kw_rows}")
            
            # Fetch in-degree (incoming graph links)
            cur.execute("SELECT COUNT(*) FROM channel_graph WHERE target_channel_id = %s", (lead_id,))
            in_degree = cur.fetchone()[0]
            print(f"In-Degree: {in_degree}")
            
        else:
            print(f"=================================")
            print(f"@{username} NOT FOUND in leads table.")
            
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
