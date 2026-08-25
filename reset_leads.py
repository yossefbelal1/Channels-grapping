import psycopg2

try:
    conn = psycopg2.connect("postgresql://postgres:leadhunter_pass@postgres/leadhunter_db")
    cur = conn.cursor()
    cur.execute("UPDATE leads SET last_scan = NULL WHERE status = 'new' AND lead_score IS NULL")
    conn.commit()
    print(f"Successfully reset last_scan to NULL for {cur.rowcount} stubs.")
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error resetting leads: {e}")
