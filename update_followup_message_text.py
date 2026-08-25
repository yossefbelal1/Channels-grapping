"""
Update follow-up campaign message text in PostgreSQL campaigns table.
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "dbname": os.getenv("DB_NAME", "leadhunter_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "postgres"),
}

NEW_FOLLOWUP_TEXT = """السلام عليكم يا غالي 🤝
حبيت أتأكد إن العرض وصلك، الصور المرفقة دي نتائج حقيقية لقنوات مسكناها.

القناة بدون ترافيك وإعلانات مستمرة نموها بيقف تماماً، ومصلحتك تكون معايا لأن انا الترس ال بيشغل القناة و بيجلك الاعضاء و الترافيك اللي هتضمن لقناتك ترند صاعد مستمر ومتداولين جدد للـ VIP وإدارة الحسابات:

• تجربة مجانية بالكامل بدون أي التزام مالي.
• شبكة تضم +100 قناة فوركس وتداول نشطة.

أرسل رابط قناتك نجرب والنتائج هي اللي تحكم وللتفاصيل اكتر: @tamerads1"""

MEDIA_ALBUM_PATHS = "/app/media/proof_1.jpg,/app/media/proof_2.jpg,/app/media/proof_3.jpg"

def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT id, followup_media_path FROM campaigns ORDER BY created_at DESC LIMIT 1")
    row = cur.fetchone()
    if not row:
        print("No active campaign found!")
        conn.close()
        return

    cid = row['id']
    print(f"Updating Campaign ID: {cid}")

    cur.execute("""
        UPDATE campaigns
        SET 
            followup_message_text = %s,
            followup_media_path = %s,
            followup_enabled = TRUE
        WHERE id = %s
    """, (NEW_FOLLOWUP_TEXT, MEDIA_ALBUM_PATHS, cid))
    conn.commit()

    print("✅ Follow-up message text and 3 images updated successfully!")

    # Verify
    cur.execute("SELECT id, followup_enabled, followup_message_text, followup_media_path FROM campaigns WHERE id = %s", (cid,))
    c = cur.fetchone()
    print("\n" + "="*50)
    print(f"Campaign ID: {c['id']}")
    print(f"Follow-up Enabled: {c['followup_enabled']}")
    print(f"3 Images Attached: {c['followup_media_path']}")
    print("New Message Text:")
    print("-" * 30)
    print(c['followup_message_text'])
    print("="*50)

    conn.close()

if __name__ == "__main__":
    main()
