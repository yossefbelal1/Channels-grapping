"""
Configure Active Campaign and Follow-up Campaign with the 3 proof images and message text.
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

FOLLOWUP_TEXT = """السلام عليكم يا غالي 🤝

بعتذر لو بكرر رسالتي، بس حبيت أتأكد إن العرض وصلك أو لو في نقطة ما كانتش واضحة؛ لأن مصلحة قناتك تهمني فعلاً.

أي قناة فوركس بدون تدفق مستمر لمتداولين جدد بتموت بالتدريج، وتعبك في التحليلات بيضيع على نفس الأعضاء القدامى.

أنت بتقدم المحتوى والصفقات، وأنا وظيفتي أكون ماكينة الترافيك اللي بتجبلك متداولين مهتمين بالـ VIP وإدارة الحسابات لزيادة دخلك وأرباحك.

مش خسران أي شيء تجرب وتشوف بنفسك:
• تجربة مجانية بالكامل بدون أي مقابل مالي.
• شبكة إعلانية تضم +100 قناة فوركس وتداول نشطة.

أرسل رابط قناتك نجرب سوا والنتائج هي اللي هتحكم: @tamerads1"""

MEDIA_ALBUM_PATHS = "/app/media/proof_1.jpg,/app/media/proof_2.jpg,/app/media/proof_3.jpg"

def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT id FROM campaigns ORDER BY created_at DESC LIMIT 1")
    row = cur.fetchone()
    if not row:
        print("No campaign found!")
        conn.close()
        return

    cid = row['id']
    print(f"Configuring Campaign ID: {cid}")

    # Update both main campaign and follow-up campaign
    cur.execute("""
        UPDATE campaigns
        SET 
            media_path = %s,
            followup_message_text = %s,
            followup_media_path = %s,
            followup_enabled = TRUE,
            followup_delay_days = 4
        WHERE id = %s
    """, (MEDIA_ALBUM_PATHS, FOLLOWUP_TEXT, MEDIA_ALBUM_PATHS, cid))
    conn.commit()

    print("✅ Successfully configured both campaigns with 3 images!")

    # Verify
    cur.execute("SELECT id, message_text, media_path, followup_enabled, followup_message_text, followup_media_path, followup_delay_days FROM campaigns WHERE id = %s", (cid,))
    c = cur.fetchone()
    print("\n" + "="*60)
    print("📢 MAIN CAMPAIGN (New Leads - 12/day):")
    print(f"  • Media: {c['media_path']}")
    print(f"  • Message Preview: {c['message_text'][:60]}...")
    print("\n🔁 FOLLOW-UP CAMPAIGN (Unanswered Leads - 8/day):")
    print(f"  • Enabled: {c['followup_enabled']}")
    print(f"  • Delay: {c['followup_delay_days']} days")
    print(f"  • Media: {c['followup_media_path']}")
    print(f"  • Message Preview: {c['followup_message_text'][:60]}...")
    print("="*60)

    # Check stats
    cur.execute("""
        SELECT 
            COUNT(*) FILTER (WHERE status = 'pending') as new_pending,
            COUNT(*) FILTER (WHERE status = 'sent') as total_sent,
            COUNT(*) FILTER (WHERE status = 'sent' AND (followup_status IS NULL OR followup_status = 'pending') AND user_replied = FALSE AND sent_at < NOW() - INTERVAL '4 days') as followup_ready_now,
            COUNT(*) FILTER (WHERE followup_status = 'sent') as followup_already_sent
        FROM campaign_logs
        WHERE campaign_id = %s
    """, (cid,))
    stats = cur.fetchone()
    print(f"\n📊 STATS:")
    print(f"  • New Leads Pending: {stats['new_pending']}")
    print(f"  • Total Previously Sent: {stats['total_sent']}")
    print(f"  • Follow-ups Ready to send now (>4 days): {stats['followup_ready_now']}")
    print(f"  • Follow-ups already sent: {stats['followup_already_sent']}")

    conn.close()

if __name__ == "__main__":
    main()
