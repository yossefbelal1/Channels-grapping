import asyncio
import os
from telethon import TelegramClient
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID", "32950512"))
API_HASH = os.getenv("API_HASH", "23f5be247297fe7645193f6f782dad67")
SESSION = os.path.join("sessions", "user_session")

async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        print("Client not authorized!")
        return

    me = await client.get_me()
    print(f"User: {me.first_name} (@{me.username}) | ID: {me.id} | Restricted: {me.restricted}")

    # Send message to SpamBot to check restriction status
    try:
        async with client.conversation('SpamBot') as conv:
            await conv.send_message('/start')
            resp = await conv.get_response()
            print(f"\n[SpamBot Response]:\n{resp.text}\n")
    except Exception as e:
        print(f"Error checking SpamBot: {e}")

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
