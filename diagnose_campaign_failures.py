"""
Diagnose failed campaign sends for campaign 30d91eeb.
- Shows failure reason for each failed channel
- Gets channel username/invite link
- Exports to CSV for manual outreach
"""
import asyncio
import sys
import os
import csv
from datetime import datetime
import psycopg2
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from tg_manager import get_session_path

# DB connection
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "dbname": os.getenv("DB_NAME", "leadhunter"),
    "user": os.getenv("DB_USER", "leadhunter"),
    "password": os.getenv("DB_PASSWORD", "leadhunter"),
}

CAMPAIGN_ID = "30d91eeb"  # partial ID prefix

async def main():
    # Connect to DB
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Find full campaign ID
    cur.execute("SELECT id, message_text FROM campaigns WHERE id::text LIKE %s LIMIT 1", (CAMPAIGN_ID + '%',))
    row = cur.fetchone()
    if not row:
        print(f"Campaign {CAMPAIGN_ID} not found!")
        conn.close()
        return
    campaign_id, msg_text = row
    print(f"Campaign: {campaign_id}")
    print(f"Message: {msg_text[:80]}...")

    # Get failed sends with channel info
    print("\nFetching failed sends...")
    cur.execute("""
        SELECT
            cl.id,
            cl.lead_id,
            cl.status,
            cl.error_message,
            cl.sent_at,
            l.channel_username,
            l.member_count,
            l.description
        FROM campaign_logs cl
        LEFT JOIN leads l ON l.id = cl.lead_id
        WHERE cl.campaign_id = %s
          AND cl.status IN ('FAILED', 'ERROR', 'failed', 'error')
        ORDER BY l.member_count DESC NULLS LAST
    """, (campaign_id,))
    failed_rows = cur.fetchall()
    print(f"Failed sends: {len(failed_rows)}")

    # Count by error type
    error_counts = {}
    for row in failed_rows:
        err = row[3] or "Unknown"
        if 'PEER_ID_INVALID' in str(err): key = 'PEER_ID_INVALID (not in session cache)'
        elif 'CHAT_WRITE_FORBIDDEN' in str(err): key = 'CHAT_WRITE_FORBIDDEN (no post permission)'
        elif 'CHANNEL_PRIVATE' in str(err): key = 'CHANNEL_PRIVATE'
        elif 'USER_BANNED' in str(err): key = 'USER_BANNED_IN_CHANNEL'
        elif 'FLOOD' in str(err): key = 'FLOOD_WAIT (rate limited)'
        elif 'not a member' in str(err).lower(): key = 'Not a member'
        elif 'banned' in str(err).lower(): key = 'Banned'
        elif 'restricted' in str(err).lower(): key = 'Restricted'
        elif 'InputPeerChannel' in str(err): key = 'Bad peer (not joined/cached)'
        else: key = str(err)[:60]
        error_counts[key] = error_counts.get(key, 0) + 1

    print("\n=== FAILURE REASONS BREAKDOWN ===")
    for err, count in sorted(error_counts.items(), key=lambda x: -x[1]):
        print(f"  {count:4d}x  {err}")

    # Export to CSV
    output_file = "/app/failed_channels_export.csv"
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['channel_username', 'telegram_link', 'member_count', 'error', 'failed_at'])
        for row in failed_rows:
            log_id, lead_id, status, error, sent_at, username, member_count, desc = row
            link = f"https://t.me/{username}" if username else ""
            writer.writerow([username or '', link, member_count or 0, error or '', sent_at or ''])

    print(f"\n✅ CSV exported to: {output_file}")

    # Show top 50 failed channels
    print("\n=== TOP FAILED CHANNELS (sorted by member count) ===")
    for i, row in enumerate(failed_rows[:50], 1):
        log_id, lead_id, status, error, sent_at, username, member_count, desc = row
        link = f"t.me/{username}" if username else "no-link"
        err_short = str(error or "?")[:50]
        print(f"  {i:2d}. @{username or 'unknown':35s} | {member_count or 0:7,} members | {err_short}")

    conn.close()
    print(f"\nTotal failed: {len(failed_rows)}")
    print("Done.")

if __name__ == "__main__":
    asyncio.run(main())
