import asyncio
import json
import os
import sys
from telethon import TelegramClient

sys.path.insert(0, '/app')
from tg_manager import get_session_path

async def test():
    with open('/app/accounts.json') as f:
        accs = json.load(f)
    for a in accs:
        sname = a['session_name']
        spath = get_session_path(sname)
        c = TelegramClient(spath, a['api_id'], a['api_hash'])
        try:
            await c.connect()
            auth = await c.is_user_authorized()
            me = await c.get_me() if auth else None
            await c.disconnect()
            uname = me.username if me and me.username else (me.phone if me else "None")
            print(f"RESULT: {sname} -> auth={auth}, user={uname}")
        except Exception as e:
            print(f"RESULT: {sname} -> ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(test())
