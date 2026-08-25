import asyncio
import os
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

    dialogs_active = await client.get_dialogs(limit=None)
    dialogs_archived = await client.get_dialogs(limit=None, folder=1)
    all_dialogs = dialogs_active + dialogs_archived
    dialog_map = {}
    for d in all_dialogs:
        p_id = getattr(d.input_entity, 'channel_id', None) or getattr(d.input_entity, 'chat_id', None) or getattr(d.input_entity, 'user_id', None) or getattr(d.input_entity, 'id', None)
        if p_id:
            dialog_map[p_id] = d

    print(f"=== BREAKDOWN OF ALL FOLDERS AND ADMIN PEERS ===")
    for f in filters:
        if not hasattr(f, 'title'):
            continue
        title = f.title.text if hasattr(f.title, 'text') else str(f.title)
        f_id = getattr(f, 'id', 'N/A')
        peers = getattr(f, 'include_peers', [])
        
        admin_count = 0
        non_admin_count = 0
        unknown_count = 0
        for peer in peers:
            p_id = getattr(peer, 'channel_id', None) or getattr(peer, 'chat_id', None) or getattr(peer, 'user_id', None) or getattr(peer, 'id', None)
            d = dialog_map.get(p_id)
            if d:
                entity = d.entity
                creator = getattr(entity, 'creator', False)
                left = getattr(entity, 'left', False)
                kicked = getattr(entity, 'kicked', False)
                admin_rights = getattr(entity, 'admin_rights', None) is not None
                if not left and not kicked and (creator or admin_rights):
                    admin_count += 1
                else:
                    non_admin_count += 1
            else:
                unknown_count += 1
        
        print(f"Folder ID: {f_id:3d} | Title: '{title}' | Total: {len(peers):2d} | Admin: {admin_count:2d} | Non-Admin: {non_admin_count:2d} | Not in Dialogs: {unknown_count:2d}")

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
