import asyncio
import os
import sys
from telethon import TelegramClient

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from tg_manager import get_session_path

async def main():
    session_path = get_session_path("user_session")
    client = TelegramClient(session_path, 36318125, '5f2ea025376141a257979750c3fc9cf7')
    await client.connect()
    if not await client.is_user_authorized():
        print("user_session NOT authorized!")
        await client.disconnect()
        return

    import telethon.tl.functions.messages as messages_fn

    print("Fetching dialog filters to get folder 122 structure...")
    res = await client(messages_fn.GetDialogFiltersRequest())
    my_filter = None
    for f in res.filters:
        if getattr(f, 'id', None) == 122:
            my_filter = f
            break

    if my_filter:
        print(f"\n🎉 TELEGRAM SERVER FOLDER STRUCTURE CONFIRMATION:")
        print(f"   Folder ID: 122")
        print(f"   Title: '{getattr(my_filter.title, 'text', my_filter.title)}'")
        print(f"   Broadcasts Flag: {getattr(my_filter, 'broadcasts', False)}")
        print(f"   Groups Flag: {getattr(my_filter, 'groups', False)}")
        print(f"   Excluded Non-Admin Peers: {len(getattr(my_filter, 'exclude_peers', []))}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
