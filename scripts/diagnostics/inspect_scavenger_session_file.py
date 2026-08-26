import sqlite3
import os

session_path = "sessions/scavenger_session.session"
if not os.path.exists(session_path):
    session_path = "scavenger_session.session"

print(f"Reading sqlite session file: {session_path}")
conn = sqlite3.connect(session_path)
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cur.fetchall()
print(f"Tables: {tables}")

for t in tables:
    t_name = t[0]
    print(f"\n--- Table: {t_name} ---")
    cur.execute(f"SELECT * FROM {t_name}")
    rows = cur.fetchall()
    for r in rows:
        print(r)

conn.close()
