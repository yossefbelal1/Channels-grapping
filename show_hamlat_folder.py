"""
Show what's currently in the 'حملات' folder and list all admin channels
so user can pick which ones to add.
"""
import asyncio
import os
import sys
from telethon import TelegramClient
from telethon.tl.functions.messages import GetDialogFiltersRequest
from telethon.tl.types import DialogFilter, Channel, Chat

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from tg_manager import get_session_path

async def main():
    session_path = get_session_path("user_session")
    client = TelegramClient(session_path, 36318125, '5f2ea025376141a257979750c3fc9cf7')
    await client.connect()

    res = await client(GetDialogFiltersRequest())
    for f in res.filters:
        if getattr(f, 'title', None) and getattr(f.title, 'text', '') == 'حملات':
            peers = getattr(f, 'include_peers', [])
            print(f"📁 حملات (ID={f.id}) — {len(peers)} peer(s) saved:")
            for ip in peers:
                try:
                    ent = await client.get_entity(ip)
                    print(f"  - {getattr(ent, 'title', str(ent.id))} (ID={ent.id})")
                except Exception as e:
                    print(f"  - Unknown peer: {ip} ({e})")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
