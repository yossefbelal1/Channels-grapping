import psycopg2

conn = psycopg2.connect("postgresql://postgres:leadhunter_pass@postgres/leadhunter_db")
cur = conn.cursor()
cur.execute("SELECT lead_score, COUNT(1) FROM leads WHERE status = 'new' GROUP BY lead_score ORDER BY lead_score DESC NULLS LAST")
results = cur.fetchall()
print("Lead Score distribution for status = 'new':")
for r in results:
    print(r)
