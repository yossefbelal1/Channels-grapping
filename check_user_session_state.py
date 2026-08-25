import asyncio
from telethon import TelegramClient

async def check():
    c = TelegramClient('/app/sessions/user_session', 36318125, '5f2ea025376141a257979750c3fc9cf7')
    await c.connect()
    auth = await c.is_user_authorized()
    me = await c.get_me() if auth else None
    await c.disconnect()
    print("USER_SESSION_AUTH:", auth)
    if me:
        print("USER_SESSION_ME:", me.first_name, f"(@{me.username})", me.phone)

if __name__ == "__main__":
    asyncio.run(check())
