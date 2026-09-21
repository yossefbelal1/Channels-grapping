import asyncio
from telethon import TelegramClient

async def test_session(sname):
    print(f"Testing {sname}...")
    try:
        client = TelegramClient(f'/app/sessions/{sname}', 39064636, '72d90d8ac46e9293e3d5254d9645e4f9')
        await client.connect()
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"  [OK] {sname}: Authorized as {me.first_name} (@{me.username}) Phone: {me.phone}")
        else:
            print(f"  [FAIL] {sname}: Not authorized")
        await client.disconnect()
    except Exception as e:
        print(f"  [ERROR] {sname}: {e}")

async def main():
    for s in ['acc_12723433281', 'acc_14809564829', 'scavenger_session', 'radar_session', 'validator_session']:
        await test_session(s)

if __name__ == '__main__':
    asyncio.run(main())
