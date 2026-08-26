import asyncio
import os
import sys
import glob
from telethon import TelegramClient

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

async def main():
    sessions = glob.glob("sessions/*.session") + glob.glob("*.session")
    session_names = sorted(list(set([os.path.splitext(os.path.basename(s))[0] for s in sessions])))

    print(f"Found session files: {session_names}\n")

    for s_name in session_names:
        # construct relative path without extension for telethon
        s_path = os.path.join("sessions", s_name) if os.path.exists(os.path.join("sessions", f"{s_name}.session")) else s_name
        try:
            client = TelegramClient(s_path, 36318125, '5f2ea025376141a257979750c3fc9cf7')
            await client.connect()
            if await client.is_user_authorized():
                me = await client.get_me()
                fname = getattr(me, 'first_name', '') or ''
                lname = getattr(me, 'last_name', '') or ''
                uname = getattr(me, 'username', 'No Username')
                phone = getattr(me, 'phone', 'No Phone')
                full_name = f"{fname} {lname}".strip()
                print(f"★ Session: {s_name}")
                print(f"   Name: '{full_name}'")
                print(f"   Username: @{uname}")
                print(f"   Phone: +{phone}")
                print(f"   User ID: {me.id}\n")
            else:
                print(f"⚠️ Session: {s_name} - Not Authorized\n")
            await client.disconnect()
        except Exception as e:
            print(f"❌ Session: {s_name} - Error: {e}\n")

if __name__ == "__main__":
    asyncio.run(main())
