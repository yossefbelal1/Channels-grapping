import asyncio
import json
from telethon import TelegramClient
from tg_manager import get_session_path

async def main():
    with open('/app/accounts.json') as f:
        accs = json.load(f)
    for a in accs:
        name = a['session_name']
        c = TelegramClient(get_session_path(name), a['api_id'], a['api_hash'])
        try:
            await c.connect()
            auth = await c.is_user_authorized()
            me = await c.get_me() if auth else None
            await c.disconnect()
            info = f"@{me.username}" if (me and me.username) else (me.phone if me else "")
            print(f"SESSION_CHECK: {name} -> Authorized: {auth} ({info})")
        except Exception as e:
            print(f"SESSION_CHECK: {name} -> ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(main())
