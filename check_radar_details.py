import asyncio
import os
import sys
from telethon import TelegramClient

async def main():
    s_path = os.path.join("sessions", "radar_session")
    client = TelegramClient(s_path, 31925523, '6448299ee7fb91c63cbc82511b435594')
    await client.connect()
    if await client.is_user_authorized():
        me = await client.get_me()
        fname = getattr(me, 'first_name', '') or ''
        lname = getattr(me, 'last_name', '') or ''
        uname = getattr(me, 'username', 'No Username')
        phone = getattr(me, 'phone', 'No Phone')
        full_name = f"{fname} {lname}".strip()
        print(f"★ Session: radar_session")
        print(f"   Name: '{full_name}'")
        print(f"   Username: @{uname}")
        print(f"   Phone: +{phone}")
        print(f"   User ID: {me.id}\n")
    else:
        print("radar_session NOT authorized")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
