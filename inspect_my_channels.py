import asyncio
import os
import sys
from telethon import TelegramClient
from telethon.tl.functions.messages import GetDialogFiltersRequest
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

    res_filters = await client(GetDialogFiltersRequest())
    filters = res_filters.filters if hasattr(res_filters, 'filters') else []
    
    my_channels_filter = None
    for f in filters:
        title = f.title.text if hasattr(f.title, 'text') else str(f.title)
        if title == "My_Channels":
            my_channels_filter = f
            break

    if not my_channels_filter:
        print("Folder 'My_Channels' not found!")
        await client.disconnect()
        return

    print(f"Total peers in 'My_Channels' folder: {len(my_channels_filter.include_peers)}")
    
    # Get all dialogs
    dialogs_active = await client.get_dialogs(limit=None)
    dialogs_archived = await client.get_dialogs(limit=None, folder=1)
    all_dialogs = dialogs_active + dialogs_archived
    dialog_map = {}
    for d in all_dialogs:
        p_id = getattr(d.input_entity, 'channel_id', None) or getattr(d.input_entity, 'chat_id', None) or getattr(d.input_entity, 'user_id', None) or getattr(d.input_entity, 'id', None)
        if p_id:
            dialog_map[p_id] = d

    count = 0
    for peer in my_channels_filter.include_peers:
        count += 1
        p_id = getattr(peer, 'channel_id', None) or getattr(peer, 'chat_id', None) or getattr(peer, 'user_id', None) or getattr(peer, 'id', None)
        peer_type = peer.__class__.__name__
        d = dialog_map.get(p_id)
        if d:
            entity = d.entity
            creator = getattr(entity, 'creator', False)
            admin_rights = getattr(entity, 'admin_rights', None)
            username = getattr(entity, 'username', 'N/A')
            title = d.name
            print(f"[{count:02d}] ID: {p_id} | Type: {peer_type} | Username: @{username} | Creator: {creator} | AdminRights: {admin_rights is not None} | Title: {title}")
        else:
            print(f"[{count:02d}] ID: {p_id} | Type: {peer_type} | NOT IN DIALOGS LIST")

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
