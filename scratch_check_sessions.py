import os
import json
import asyncio
from telethon import TelegramClient

async def check_session(session_path, api_id, api_hash):
    client = TelegramClient(session_path, api_id, api_hash)
    try:
        await client.connect()
        authorized = await client.is_user_authorized()
        print(f"Session {os.path.basename(session_path)}: Authorized={authorized}")
        await client.disconnect()
        return authorized
    except Exception as e:
        print(f"Session {os.path.basename(session_path)}: Error={e}")
        return False

async def main():
    json_path = "accounts.json"
    accounts = {}
    if os.path.exists(json_path):
        with open(json_path, 'r') as f:
            acc_list = json.load(f)
            for acc in acc_list:
                accounts[acc["session_name"]] = (acc["api_id"], acc["api_hash"])
    
    # Defaults/Fallbacks from environment
    api_id = int(os.getenv("API_ID", 0))
    api_hash = os.getenv("API_HASH", "")
    
    session_dir = "sessions"
    if os.path.exists(session_dir):
        files = [f for f in os.listdir(session_dir) if f.endswith(".session")]
        for f in files:
            name = f[:-8]
            path = os.path.join(session_dir, name)
            aid, ahash = accounts.get(name, (api_id, api_hash))
            if not aid or not ahash:
                print(f"Session {f}: Missing API ID/Hash in accounts.json and .env")
                continue
            await check_session(path, aid, ahash)

if __name__ == "__main__":
    asyncio.run(main())
