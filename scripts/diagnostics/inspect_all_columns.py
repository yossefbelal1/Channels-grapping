import os
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "postgres"),
    port=int(os.getenv("DB_PORT", "5432")),
    dbname=os.getenv("DB_NAME", "leadhunter_db"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", "leadhunter_pass")
)
cur = conn.cursor(cursor_factory=RealDictCursor)

cur.execute("""
    SELECT table_name, column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema = 'public'
    ORDER BY table_name, ordinal_position;
""")
cols = cur.fetchall()
for c in cols:
    print(f"{c['table_name']}.{c['column_name']} ({c['data_type']})")
