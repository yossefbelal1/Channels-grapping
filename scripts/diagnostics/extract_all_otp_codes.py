import asyncio
import os
import sys
import glob
import re
from telethon import TelegramClient

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
    },
    {
        "phone": "fallback",
        "api_id": 36318125,
        "api_hash": "5f2ea025376141a257979750c3fc9cf7"
    }
]

async def check_session(s_path):
    print(f"\n=======================================================")
    print(f"Checking session file: {s_path}")
    print(f"=======================================================")
    
    for acc in ACCOUNTS:
        try:
            client = TelegramClient(s_path, acc["api_id"], acc["api_hash"])
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                continue
            
            me = await client.get_me()
            phone = getattr(me, 'phone', '')
            name = f"{getattr(me, 'first_name', '')} {getattr(me, 'last_name', '')}".strip()
            print(f"[*] AUTHORIZED SESSION: '{s_path}'")
            print(f"[*] User: {name} | Phone: +{phone} | ID: {me.id}")
            
            # Fetch latest 10 messages from 777000 (Telegram official notifications)
            try:
                msgs = await client.get_messages(777000, limit=10)
                if msgs:
                    print(f"\n>>> Telegram Service Messages (777000) for +{phone}:")
                    for m in msgs:
                        date_str = m.date.strftime("%Y-%m-%d %H:%M:%S UTC")
                        # Extract any numbers/codes
                        print(f"--- Message ID: {m.id} | Date: {date_str} ---")
                        # Safe print text
                        safe_text = m.text.encode('utf-8', errors='replace').decode('utf-8')
                        print(safe_text)
                        print("-" * 40)
                else:
                    print(f"No messages from 777000.")
            except Exception as msg_err:
                print(f"Could not fetch 777000 messages: {msg_err}")
                
            await client.disconnect()
            return  # Stop once authorized with an account
        except Exception as e:
            # print error only if not just connection retry
            pass

async def main():
    search_dirs = ["sessions", "/root/Channels-grapping/sessions", "."]
    session_files = []
    for d in search_dirs:
        if os.path.exists(d):
            session_files.extend(glob.glob(f"{d}/*.session"))
            
    session_files = sorted(list(set(session_files)))
    print(f"Found session files: {session_files}")
    
    for s_file in session_files:
        # pass path without .session extension
        s_path = os.path.splitext(s_file)[0]
        await check_session(s_path)

if __name__ == "__main__":
    asyncio.run(main())
