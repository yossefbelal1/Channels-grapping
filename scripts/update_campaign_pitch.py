"""
Update the active campaign auto-reply message text to question format.
"""
import os
import psycopg2

DB_HOST = os.getenv("DB_HOST", "postgres")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "leadhunter_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "leadhunter_pass")

NEW_PITCH_TEXT = """محتاج مدير اعلانات؟؟؟.  شغلي تبادل اعلاني استهداف اعضاء يخصوا مجال قناتك.
 فيه ---فترة تجريبية مجانا--- للتاكد من شغلي

 و دي بعض صور نمو قنواتنا"""

def main():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    cur = conn.cursor()
    cur.execute("UPDATE campaigns SET auto_reply_message_text = %s WHERE status = 'active';", (NEW_PITCH_TEXT,))
    conn.commit()
    print(f"Updated {cur.rowcount} active campaign(s).")
    
    cur.execute("SELECT id, status, auto_reply_message_text, auto_reply_media_path FROM campaigns WHERE status = 'active';")
    rows = cur.fetchall()
    for row in rows:
        print(f"Campaign ID: {row[0]}")
        print(f"Status: {row[1]}")
        print(f"Text:\n{row[2]}")
        print(f"Media:\n{row[3]}")
    conn.close()

if __name__ == "__main__":
    main()
