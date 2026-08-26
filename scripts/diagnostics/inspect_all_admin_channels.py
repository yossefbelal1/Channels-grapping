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

    # 1. Fetch all dialogs (active + archived)
    dialogs_active = await client.get_dialogs(limit=None)
    dialogs_archived = await client.get_dialogs(limit=None, folder=1)
    all_dialogs = dialogs_active + dialogs_archived
    print(f"Fetched {len(all_dialogs)} total dialogs.")

    # 2. Fetch all folders
    res_filters = await client(GetDialogFiltersRequest())
    filters = res_filters.filters if hasattr(res_filters, 'filters') else []

    # Map peer_id -> list of folder titles it belongs to
    peer_folders_map = {}
    folder_map = {}
    for f in filters:
        if not hasattr(f, 'title'):
            continue
        title = f.title.text if hasattr(f.title, 'text') else str(f.title)
        folder_map[f.id] = title
        for peer in getattr(f, 'include_peers', []):
            p_id = getattr(peer, 'channel_id', None) or getattr(peer, 'chat_id', None) or getattr(peer, 'user_id', None) or getattr(peer, 'id', None)
            if p_id:
                if p_id not in peer_folders_map:
                    peer_folders_map[p_id] = []
                peer_folders_map[p_id].append(title)

    admin_channels = []
    for d in all_dialogs:
        if not (d.is_channel or d.is_group):
            continue
        entity = d.entity
        left = getattr(entity, 'left', False)
        kicked = getattr(entity, 'kicked', False)
        creator = getattr(entity, 'creator', False)
        admin_rights = getattr(entity, 'admin_rights', None)
        
        is_admin = False
        if not left and not kicked:
            if creator or admin_rights is not None:
                is_admin = True

        if is_admin:
            p_id = getattr(d.input_entity, 'channel_id', None) or getattr(d.input_entity, 'chat_id', None) or getattr(d.input_entity, 'id', None)
            username = getattr(entity, 'username', 'N/A')
            folders = peer_folders_map.get(p_id, [])
            admin_channels.append({
                'id': p_id,
                'name': d.name,
                'username': username,
                'creator': creator,
                'admin_rights': admin_rights is not None,
                'folders': folders
            })

    print(f"\n=== TOTAL ADMIN CHANNELS/GROUPS FOUND: {len(admin_channels)} ===")
    for idx, c in enumerate(admin_channels, 1):
        folders_str = ", ".join(c['folders']) if c['folders'] else "NO FOLDER"
        print(f"[{idx:02d}] ID: {c['id']} | @{c['username']} | Creator: {c['creator']} | Admin: {c['admin_rights']} | Folders: [{folders_str}] | Title: {c['name']}")

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
