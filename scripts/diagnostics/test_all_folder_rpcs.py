import asyncio
import os
from telethon import TelegramClient
from telethon.tl.functions.messages import UpdateDialogFilterRequest
from telethon.tl.types import DialogFilter, TextWithEntities, InputPeerSelf
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

    # Test creating a new folder
    try:
        print("Testing creating new folder id=199 via UpdateDialogFilterRequest...")
        test_filter = DialogFilter(
            id=199,
            title=TextWithEntities(text="Test_Folder", entities=[]),
            pinned_peers=[],
            include_peers=[InputPeerSelf()],
            exclude_peers=[],
            contacts=False, non_contacts=False, groups=False, broadcasts=False, bots=False,
            exclude_muted=False, exclude_read=False, exclude_archived=False
        )
        res = await client(UpdateDialogFilterRequest(id=199, filter=test_filter))
        print(f"Success creating new folder! Result: {res}")
        # Clean up
        await client(UpdateDialogFilterRequest(id=199, filter=None))
    except Exception as e:
        print(f"Failed creating new folder: {type(e).__name__} - {e}")

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
