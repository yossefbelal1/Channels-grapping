import asyncio
import os
import sys
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

API_ID = 36318125
API_HASH = '5f2ea025376141a257979750c3fc9cf7'
PHONE = '+201207500631'
SESSION_PATH = '/app/sessions/user_session'

async def main():
    # Delete old session file if exists
    session_file = SESSION_PATH + '.session'
    if os.path.exists(session_file):
        os.remove(session_file)
        print(f"✓ Deleted old session file: {session_file}")

    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
    await client.connect()

    print(f"Requesting login code for {PHONE}...")
    await client.send_code_request(PHONE)

    code = input("Enter the OTP code you received on Telegram: ").strip()

    try:
        await client.sign_in(PHONE, code)
        print("✓ Signed in successfully!")
    except SessionPasswordNeededError:
        password = input("2FA Password required. Enter your password: ").strip()
        await client.sign_in(password=password)
        print("✓ Signed in with 2FA successfully!")

    me = await client.get_me()
    is_premium = getattr(me, 'premium', False)
    print(f"\n🎉 SESSION REFRESHED SUCCESSFULLY!")
    print(f"   User: {me.first_name} (@{me.username})")
    print(f"   Phone: {me.phone}")
    print(f"   Telegram Premium: {is_premium}")

    await client.disconnect()
    print("\n✓ New session saved to: " + session_file)

if __name__ == "__main__":
    asyncio.run(main())
