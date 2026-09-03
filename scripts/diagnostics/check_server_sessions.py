import asyncio
import os
import glob
from telethon import TelegramClient

ACCOUNTS = [
    {"name": "radar_session", "api_id": 31925523, "api_hash": "6448299ee7fb91c63cbc82511b435594"},
    {"name": "validator_session", "api_id": 39064636, "api_hash": "72d90d8ac46e9293e3d5254d9645e4f9"},
    {"name": "scavenger_session", "api_id": 31925523, "api_hash": "6448299ee7fb91c63cbc82511b435594"},
    {"name": "user_session", "api_id": 39064636, "api_hash": "72d90d8ac46e9293e3d5254d9645e4f9"},
    {"name": "test_session", "api_id": 39064636, "api_hash": "72d90d8ac46e9293e3d5254d9645e4f9"},
]

async def check():
    for acc in ACCOUNTS:
        sess_path = f"/app/sessions/{acc['name']}"
        if not os.path.exists(f"{sess_path}.session"):
            print(f"[-] {acc['name']}: session file not found")
            continue
        try:
            client = TelegramClient(sess_path, acc['api_id'], acc['api_hash'])
            await client.connect()
            if await client.is_user_authorized():
                me = await client.get_me()
                print(f"[+] {acc['name']}: AUTHORIZED -> {me.first_name} (+{getattr(me, 'phone', 'Unknown')})")
            else:
                print(f"[-] {acc['name']}: NOT AUTHORIZED")
            await client.disconnect()
        except Exception as e:
            print(f"[!] {acc['name']}: ERROR -> {e}")

if __name__ == "__main__":
    asyncio.run(check())
