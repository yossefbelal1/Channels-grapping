import asyncio
import os
from telethon import TelegramClient

sessions = [
    ("radar_session", 2040, "b18441a1ff607e10a989891a5462e627"),
    ("scavenger_session", 2040, "b18441a1ff607e10a989891a5462e627"),
    ("validator_session", 2040, "b18441a1ff607e10a989891a5462e627"),
    ("user_session", 36318125, "5f2ea025376141a257979750c3fc9cf7"),
    ("acc_12723433281", 2040, "b18441a1ff607e10a989891a5462e627"),
    ("acc_14809564829", 2040, "b18441a1ff607e10a989891a5462e627"),
]

async def check():
    for name, api_id, api_hash in sessions:
        path = f"sessions/{name}.session"
        if not os.path.exists(path):
            print(f"{name}: NOT FOUND at {path}")
            continue
        try:
            client = TelegramClient(f"sessions/{name}", api_id, api_hash)
            await client.connect()
            auth = await client.is_user_authorized()
            me = await client.get_me() if auth else None
            username = getattr(me, "username", None) if me else None
            first_name = getattr(me, "first_name", None) if me else None
            user_id = getattr(me, "id", None) if me else None
            print(f"{name}: authorized={auth}, user={first_name} (@{username}, id={user_id})")
            await client.disconnect()
        except Exception as e:
            print(f"{name}: ERROR {e}")

if __name__ == "__main__":
    asyncio.run(check())
