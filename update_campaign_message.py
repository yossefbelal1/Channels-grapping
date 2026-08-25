import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

NEW_MESSAGE = """شريكنا العزيز، مرحبًا بك في Forex ADS

نوفر لك وصولاً مباشراً لجمهور من المتداولين المهتمين بالفوركس والأسواق المالية عبر شبكتنا الإعلانية التي تضم أكثر من 100 قناة متخصصة لدعم نمو قناتك.

📌 تفاصيل العرض التجريبي الخاص بك:
• فترة تجريبية مجانية بالكامل لمدة 30 يومًا دون أي التزام مالي
• اشتراك شهري ثابت ومناسب بقيمة 30$ فقط بعد انتهاء الفترة التجريبية
• نضمن لك جلب أعضاء حقيقيين ومستهدفين متفاعلين مع التداول
• ضبط وتطوير ريتش قناتك بشكل آمن وسريع

🔹 باقات الدعم المتاحة لتنشيط القناة:
• زيادة أعداد المتابعين المتفاعلين
• رفع معدل المشاهدات اليومية للمنشورات
• تظبيط وتنسيق القناة بخطة محتوى متكاملة
• خدمات نمو شاملة لحسابات السوشيال ميديا الخاصة بقناتك

✉️ لتفعيل الشهر المجاني وتظبيط خطة قناتك اليوم:
أرسل لنا رابط قناتك، وسنقوم بالتواصل معك لتفعيل الخدمة فوراً.
✅ @tamerads1"""

conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", 5432)),
    dbname=os.getenv("DB_NAME", "leadhunter_db"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", "")
)
conn.autocommit = True
cur = conn.cursor()

# Get the auto campaign ID from file
auto_campaign_id = None
try:
    with open("auto_campaign_id.txt", "r") as f:
        auto_campaign_id = f.read().strip()
except Exception:
    pass

if auto_campaign_id:
    # Update the campaign in PostgreSQL
    cur.execute("""
        UPDATE campaigns 
        SET message_text = %s 
        WHERE id = %s
    """, (NEW_MESSAGE, auto_campaign_id))
    print(f"[+] Updated campaign {auto_campaign_id} message text successfully!")
else:
    # Create or update active campaign
    cur.execute("""
        INSERT INTO campaigns (id, message_text, media_path, status, created_at)
        VALUES (gen_random_uuid(), %s, NULL, 'active', NOW())
        ON CONFLICT DO UPDATE SET message_text = EXCLUDED.message_text
        RETURNING id
    """, (NEW_MESSAGE,))
    auto_campaign_id = cur.fetchone()[0]
    with open("auto_campaign_id.txt", "w") as f:
        f.write(str(auto_campaign_id))
    print(f"[+] Created/Updated active campaign {auto_campaign_id} with new message text!")

cur.close()
conn.close()
print("\nCampaign message updated successfully!")
