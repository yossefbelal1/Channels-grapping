import asyncio
import os
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

API_ID = 36318125
API_HASH = '5f2ea025376141a257979750c3fc9cf7'
PHONE = '+201207500631'
SESSION_PATH = '/app/sessions/user_session'

async def main():
    session_file = SESSION_PATH + '.session'
    if os.path.exists(session_file):
        os.remove(session_file)
        print(f"✓ Deleted old session: {session_file}")

    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
    await client.connect()

    print(f"Requesting OTP for {PHONE}...")
    sent = await client.send_code_request(PHONE)
    print(f"Code sent via: {sent.type}")

    # Read OTP from file
    otp_file = '/tmp/tamer_otp.txt'
    print(f"Waiting for OTP in {otp_file}...")
    for i in range(60):
        await asyncio.sleep(2)
        if os.path.exists(otp_file):
            with open(otp_file, 'r') as f:
                code = f.read().strip()
            if code:
                print(f"Got OTP: {code}")
                os.remove(otp_file)
                break
        print(f"Waiting... ({i*2}s)")
    else:
        print("TIMEOUT: No OTP received in 120s")
        await client.disconnect()
        return

    try:
        await client.sign_in(PHONE, code)
        print("✓ Signed in successfully!")
    except SessionPasswordNeededError:
        pwd_file = '/tmp/tamer_pwd.txt'
        print(f"2FA needed. Put password in {pwd_file}")
        for i in range(30):
            await asyncio.sleep(2)
            if os.path.exists(pwd_file):
                with open(pwd_file, 'r') as f:
                    pwd = f.read().strip()
                if pwd:
                    os.remove(pwd_file)
                    await client.sign_in(password=pwd)
                    print("✓ 2FA login successful!")
                    break

    me = await client.get_me()
    is_premium = getattr(me, 'premium', False)
    print(f"\n🎉 NEW SESSION CREATED SUCCESSFULLY!")
    print(f"   User: {me.first_name} (@{me.username})")
    print(f"   Premium: {is_premium}")
    print(f"   Session saved: {session_file}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
