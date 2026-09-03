import asyncio
import os
import sys
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from telethon import TelegramClient

# Setup DB connection
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "leadhunter_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASSWORD", "leadhunter_pass")

MEDIA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "media"))
os.makedirs(MEDIA_DIR, exist_ok=True)

async def fetch_and_setup_campaign():
    print("=== Fetching Message & Video from Telegram Saved Messages ===")
    
    # Connect to active session
    session_path = "sessions/radar_session"
    api_id = 31925523
    api_hash = "6448299ee7fb91c63cbc82511b435594"
    
    client = TelegramClient(session_path, api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        print(f"Session {session_path} not authorized, trying validator_session...")
        await client.disconnect()
        session_path = "sessions/validator_session"
        api_id = 39064636
        api_hash = "72d90d8ac46e9293e3d5254d9645e4f9"
        client = TelegramClient(session_path, api_id, api_hash)
        await client.connect()
        
    if not await client.is_user_authorized():
        print("[-] No authorized session found to read Saved Messages.")
        return
    
    me = await client.get_me()
    print(f"[+] Connected to Telegram as: {me.first_name} (+{getattr(me, 'phone', 'Unknown')})")
    
    # Read latest messages from Saved Messages ('me')
    saved_msgs = await client.get_messages('me', limit=5)
    if not saved_msgs:
        print("[-] No messages found in Saved Messages.")
        await client.disconnect()
        return
        
    target_msg = None
    media_file_path = None
    
    for m in saved_msgs:
        if m.text or m.media:
            target_msg = m
            print(f"\n[+] Found Message in Saved Messages (ID: {m.id}, Date: {m.date})")
            print(f"Text Content:\n{m.text}\n")
            if m.media:
                print("[*] Downloading attached media (Video/Photo)...")
                media_file_path = await client.download_media(m.media, file=MEDIA_DIR)
                print(f"[+] Media downloaded successfully to: {media_file_path}")
            break
            
    await client.disconnect()
    
    if not target_msg:
        print("[-] Could not find a valid message in Saved Messages.")
        return
        
    # Read deduplicated leads
    json_path = os.path.join(os.path.dirname(__file__), "..", "..", "autotele_target_advertisers.json")
    with open(json_path, "r", encoding="utf-8") as f:
        target_leads = json.load(f)
        
    print(f"\n[+] Loaded {len(target_leads)} deduplicated advertiser leads.")
    print(f"[+] Campaign Message Text:\n{target_msg.text}")
    print(f"[+] Attached Media Path: {media_file_path}")
    print("\n[✓] Campaign is ready to be inserted and scheduled!")

if __name__ == "__main__":
    asyncio.run(fetch_and_setup_campaign())
