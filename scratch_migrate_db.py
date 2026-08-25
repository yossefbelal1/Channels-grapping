import psycopg2

try:
    conn = psycopg2.connect("postgresql://postgres:leadhunter_pass@postgres/leadhunter_db")
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("ALTER TABLE leads ADD COLUMN last_graph_scan TIMESTAMP;")
    print("Column last_graph_scan added successfully!")
except Exception as e:
    print(f"Migration result: {e}")
