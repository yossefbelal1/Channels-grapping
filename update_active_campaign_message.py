"""
Update the active campaign message text in the PostgreSQL database.
"""
import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "dbname": os.getenv("DB_NAME", "leadhunter"),
    "user": os.getenv("DB_USER", "leadhunter"),
    "password": os.getenv("DB_PASSWORD", "leadhunter"),
}

NEW_MESSAGE = """السلام عليكم انا تامر. مدير العلانات و مسوق.
معظم المعلنين بيجبولك أرقام وخلاص.. إحنا بنجبلك متداولين حقيقيين بيدخلوا صفقات ويديروا حسابات عشان قناتك تحقق أرباح فعلية.

عارف إن بنسبة كبيرة عندك معلنين حالياً، عشان كده مش طالب منك تدفع ولا دولار:

🔹 تجربة مجانية أسبوع كامل في شبكتنا (+100 قناة فوركس).
🔹 ترافيك حقيقي يستهدف مشتركين VIP وإيداعات مش مجرد عدد.
🔹 قارن تفاعل أعضائنا بالمعلن الحالي واحكم بنفسك على النتيجة.

أرسل رابط قناتك نبدأ التجربة فوراً: @tamerads1"""

def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 1. Update active / all campaigns
    cur.execute("SELECT id, message_text FROM campaigns ORDER BY created_at DESC")
    campaigns = cur.fetchall()
    
    print(f"Found {len(campaigns)} campaigns:")
    for c in campaigns:
        print(f"  - ID: {c['id']}")
        print(f"    Old Message preview: {c['message_text'][:60]}...")
        
        cur.execute("UPDATE campaigns SET message_text = %s WHERE id = %s", (NEW_MESSAGE, c['id']))
        print(f"    ✅ Updated successfully to new message!")

    conn.commit()

    # 2. Verify
    cur.execute("SELECT id, message_text FROM campaigns ORDER BY created_at DESC")
    updated = cur.fetchall()
    print("\n=== VERIFICATION ===")
    for c in updated:
        print(f"Campaign ID: {c['id']}")
        print("Updated Message Text:\n" + "-"*40)
        print(c['message_text'])
        print("-"*40)

    conn.close()
    print("\nDatabase update completed successfully!")

if __name__ == "__main__":
    main()
