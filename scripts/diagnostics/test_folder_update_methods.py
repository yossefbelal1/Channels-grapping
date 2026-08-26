import asyncio
import os
from telethon import TelegramClient
from telethon.tl.functions.messages import GetDialogFiltersRequest, UpdateDialogFilterRequest
from telethon.tl.types import DialogFilter, DialogFilterDefault, InputPeerSelf
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

    res = await client(GetDialogFiltersRequest())
    filters = res.filters if hasattr(res, 'filters') else []

    target_filter = None
    for f in filters:
        if hasattr(f, 'title'):
            t = f.title.text if hasattr(f.title, 'text') else str(f.title)
            if t == "My_Channels":
                target_filter = f
                break

    if not target_filter:
        print("Folder 'My_Channels' not found.")
        await client.disconnect()
        return

    print(f"Found Folder 'My_Channels': ID={target_filter.id}, title={target_filter.title}, current peers={len(target_filter.include_peers)}")

    # Try updating the filter with its existing filter object to test RPC call
    try:
        print("Testing UpdateDialogFilterRequest with existing filter object...")
        res_up = await client(UpdateDialogFilterRequest(id=target_filter.id, filter=target_filter))
        print(f"Success! Result: {res_up}")
    except Exception as e:
        print(f"Failed with filter=target_filter: {type(e).__name__} - {e}")

    try:
        print("Testing UpdateDialogFilterRequest with new DialogFilter object...")
        new_f = DialogFilter(
            id=target_filter.id,
            title=target_filter.title,
            pinned_peers=target_filter.pinned_peers,
            include_peers=target_filter.include_peers,
            exclude_peers=target_filter.exclude_peers,
            contacts=target_filter.contacts,
            non_contacts=target_filter.non_contacts,
            groups=target_filter.groups,
            broadcasts=target_filter.broadcasts,
            bots=target_filter.bots,
            exclude_muted=target_filter.exclude_muted,
            exclude_read=target_filter.exclude_read,
            exclude_archived=target_filter.exclude_archived
        )
        res_up2 = await client(UpdateDialogFilterRequest(id=target_filter.id, filter=new_f))
        print(f"Success with new DialogFilter! Result: {res_up2}")
    except Exception as e:
        print(f"Failed with new DialogFilter: {type(e).__name__} - {e}")

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
