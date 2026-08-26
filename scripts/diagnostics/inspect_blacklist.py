import psycopg2

try:
    conn = psycopg2.connect("postgresql://postgres:leadhunter_pass@postgres/leadhunter_db")
    cur = conn.cursor()
    
    cur.execute("SELECT description FROM leads WHERE channel_username = 'i4_3Q'")
    desc = cur.fetchone()[0] or ""
    cur.execute("SELECT message_text FROM channel_posts WHERE channel_username = 'i4_3Q'")
    posts = [p[0] for p in cur.fetchall() if p[0]]
    full_text = (desc + " " + " ".join(posts)).lower()
    
    print("Description:", desc)
    idx = full_text.find("حب")
    while idx != -1:
        print("Match Context:")
        print(full_text[max(0, idx-50):min(len(full_text), idx+50)])
        idx = full_text.find("حب", idx + 2)
        
except Exception as e:
    print(f"Error: {e}")
