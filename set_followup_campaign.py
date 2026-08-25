"""
Helper script to configure and activate/deactivate the Follow-up Campaign.
Usage:
  python set_followup_campaign.py --message "نص الرسالة" --image "/path/to/image.jpg" --delay 4 --enable
"""
import os
import sys
import argparse
import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "dbname": os.getenv("DB_NAME", "leadhunter"),
    "user": os.getenv("DB_USER", "leadhunter"),
    "password": os.getenv("DB_PASSWORD", "leadhunter"),
}

def main():
    parser = argparse.ArgumentParser(description="Configure Follow-up Campaign")
    parser.add_argument("--message", type=str, help="Follow-up message text")
    parser.add_argument("--image", type=str, default=None, help="Path to image file (optional)")
    parser.add_argument("--delay", type=int, default=4, help="Days to wait after first message before follow-up (default: 4)")
    parser.add_argument("--enable", action="store_true", help="Enable follow-up campaign")
    parser.add_argument("--disable", action="store_true", help="Disable follow-up campaign")
    parser.add_argument("--status", action="store_true", help="Show current follow-up configuration and stats")

    args = parser.parse_args()

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Get active campaign
    cur.execute("SELECT id, followup_enabled, followup_message_text, followup_media_path, followup_delay_days FROM campaigns ORDER BY created_at DESC LIMIT 1")
    campaign = cur.fetchone()
    if not campaign:
        print("No campaign found in database!")
        conn.close()
        return

    cid = campaign['id']
    print(f"Active Campaign ID: {cid}")

    if args.message:
        cur.execute("UPDATE campaigns SET followup_message_text = %s WHERE id = %s", (args.message, cid))
        print(f"✅ Updated follow-up message text.")

    if args.image is not None:
        cur.execute("UPDATE campaigns SET followup_media_path = %s WHERE id = %s", (args.image if args.image != "" else None, cid))
        print(f"✅ Updated follow-up media path: {args.image}")

    if args.delay:
        cur.execute("UPDATE campaigns SET followup_delay_days = %s WHERE id = %s", (args.delay, cid))
        print(f"✅ Updated follow-up delay: {args.delay} days.")

    if args.enable:
        cur.execute("UPDATE campaigns SET followup_enabled = TRUE WHERE id = %s", (cid,))
        print(f"🟢 Follow-up Campaign is now ENABLED!")

    if args.disable:
        cur.execute("UPDATE campaigns SET followup_enabled = FALSE WHERE id = %s", (cid,))
        print(f"🔴 Follow-up Campaign is now DISABLED.")

    conn.commit()

    # Show current status
    cur.execute("SELECT id, followup_enabled, followup_message_text, followup_media_path, followup_delay_days FROM campaigns WHERE id = %s", (cid,))
    c_updated = cur.fetchone()

    cur.execute("""
        SELECT 
            COUNT(*) FILTER (WHERE status = 'sent' AND (followup_status IS NULL OR followup_status = 'pending') AND user_replied = FALSE) as eligible_total,
            COUNT(*) FILTER (WHERE status = 'sent' AND (followup_status IS NULL OR followup_status = 'pending') AND user_replied = FALSE AND sent_at < NOW() - (COALESCE(followup_delay_days, 4) || ' days')::INTERVAL) as ready_now,
            COUNT(*) FILTER (WHERE followup_status = 'sent') as followup_sent_count,
            COUNT(*) FILTER (WHERE user_replied = TRUE) as replied_count
        FROM campaign_logs
        JOIN campaigns ON campaigns.id = campaign_logs.campaign_id
        WHERE campaigns.id = %s
    """, (cid,))
    stats = cur.fetchone()

    print("\n" + "="*50)
    print(f"📊 FOLLOW-UP CAMPAIGN STATUS:")
    print(f"  • Enabled: {'🟢 YES' if c_updated['followup_enabled'] else '🔴 NO (Waiting for message and image)'}")
    print(f"  • Delay: {c_updated['followup_delay_days']} days after initial message")
    print(f"  • Media Attached: {c_updated['followup_media_path'] or 'None (Text Only)'}")
    print(f"  • Ready to receive follow-up now: {stats['ready_now']} contacts")
    print(f"  • Total eligible for follow-up (when delay passes): {stats['eligible_total']} contacts")
    print(f"  • Follow-ups sent so far: {stats['followup_sent_count']}")
    print(f"  • Contacts who already replied: {stats['replied_count']}")
    print("="*50)
    if c_updated['followup_message_text']:
        print("Message Text:\n" + "-"*30)
        print(c_updated['followup_message_text'])
        print("-"*30)

    conn.close()

if __name__ == "__main__":
    main()
