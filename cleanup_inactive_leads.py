import psycopg2

try:
    conn = psycopg2.connect("postgresql://postgres:leadhunter_pass@postgres/leadhunter_db")
    cur = conn.cursor()
    
    # Query all scanned leads (lead_score IS NOT NULL) that are not rejected,
    # and have either last_activity is null or older than 14 days
    cur.execute("""
        SELECT channel_username, lead_score, last_activity 
        FROM leads 
        WHERE lead_score IS NOT NULL 
          AND status != 'rejected'
          AND (last_activity IS NULL OR last_activity < NOW() - INTERVAL '14 days')
    """)
    rows = cur.fetchall()
    print(f"Found {len(rows)} inactive leads currently visible on the dashboard.")
    
    for r in rows:
        username = r[0]
        score = r[1]
        last_activity = r[2]
        link = f"https://t.me/{username}"
        reason = f"inactive_channel (last activity: {last_activity})" if last_activity else "inactive_channel (no messages)"
        
        # Insert into blacklist
        cur.execute("""
            INSERT INTO blacklist (entity_username_or_link, reason, blacklisted_at)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (entity_username_or_link) 
            DO UPDATE SET reason = EXCLUDED.reason, blacklisted_at = CURRENT_TIMESTAMP;
        """, (link, reason))
        
        # Delete from leads
        cur.execute("DELETE FROM leads WHERE LOWER(channel_username) = LOWER(%s)", (username,))
        print(f"Blacklisted and removed: @{username} (Score: {score}, Last Activity: {last_activity})")
        
    conn.commit()
    print("Database cleanup completed successfully!")
except Exception as e:
    print(f"Error executing cleanup: {e}")
