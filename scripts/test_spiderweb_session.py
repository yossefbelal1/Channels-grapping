import shutil
import asyncio
from telethon import TelegramClient

shutil.copyfile('/app/sessions/acc_12723433281.session', '/app/sessions/spiderweb_session.session')

async def main():
    client = TelegramClient('/app/sessions/spiderweb_session', 39064636, '72d90d8ac46e9293e3d5254d9645e4f9')
    await client.connect()
    me = await client.get_me()
    print("SUCCESS: Connected as", me.first_name, me.phone)
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
