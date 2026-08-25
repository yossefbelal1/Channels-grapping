import os
import sys
import json
import asyncio
from telethon import TelegramClient
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from tg_manager import get_session_path

async def test_session(session_name, api_id, api_hash):
    session_path = get_session_path(session_name)
    client = TelegramClient(session_path, api_id, api_hash)
    await client.connect()
    is_auth = await client.is_user_authorized()
    me = await client.get_me() if is_auth else None
    await client.disconnect()
    return is_auth, me

async def main():
    load_dotenv()
    with open("accounts.json", "r") as f:
        accounts = json.load(f)
        
    print("--- Testing all sessions in accounts.json ---")
    for acc in accounts:
        sname = acc["session_name"]
        aid = acc["api_id"]
        ahash = acc["api_hash"]
        try:
            auth, me = await test_session(sname, aid, ahash)
            if auth:
                username = me.username if me and me.username else "NoUsername"
                phone = me.phone if me and me.phone else "NoPhone"
                print(f"✅ {sname}: AUTHORIZED! (User: @{username}, Phone: {phone})")
            else:
                print(f"❌ {sname}: NOT AUTHORIZED")
        except Exception as e:
            print(f"⚠️ {sname}: Error testing session - {e}")

if __name__ == "__main__":
    asyncio.run(main())
