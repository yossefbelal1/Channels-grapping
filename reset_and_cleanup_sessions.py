import os
import sys
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "leadhunter_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

def main():
    # 1. Reset lead statuses in PostgreSQL
    print("Connecting to PostgreSQL...")
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    cur = conn.cursor()
    
    cur.execute("UPDATE leads SET status = 'new' WHERE status = 'contacted'")
    reset_count = cur.rowcount
    
    # 2. Clear old campaign logs and campaigns
    cur.execute("TRUNCATE campaign_logs, campaigns CASCADE")
    print(f"PostgreSQL Reset complete: Reverted {reset_count} leads back to 'new' and cleared all old campaign data.")
    
    conn.commit()
    cur.close()
    conn.close()
    
    # 3. Delete old sqlite session file
    session_file = "sessions/user_session.session"
    session_journal = "sessions/user_session.session-journal"
    
    deleted_files = []
    if os.path.exists(session_file):
        os.remove(session_file)
        deleted_files.append(session_file)
    if os.path.exists(session_journal):
        os.remove(session_journal)
        deleted_files.append(session_journal)
        
    if deleted_files:
        print(f"Deleted old session files: {', '.join(deleted_files)}")
    else:
        print("No old user session file found in local directory.")

if __name__ == "__main__":
    main()
