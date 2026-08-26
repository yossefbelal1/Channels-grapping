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

    # 1. Fetch dialogs
    dialogs_active = await client.get_dialogs(limit=None)
    dialogs_archived = await client.get_dialogs(limit=None, folder=1)
    all_dialogs = dialogs_active + dialogs_archived
    dialog_map = {}
    for d in all_dialogs:
        p_id = getattr(d.input_entity, 'channel_id', None) or getattr(d.input_entity, 'chat_id', None) or getattr(d.input_entity, 'user_id', None) or getattr(d.input_entity, 'id', None)
        if p_id:
            dialog_map[p_id] = d

    # 2. Get folder My_Channels
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

    print(f"Folder 'My_Channels' contains {len(target_filter.include_peers)} peers total.\n")

    extra_channels = []
    admin_channels = []

    for idx, peer in enumerate(target_filter.include_peers, 1):
        p_id = getattr(peer, 'channel_id', None) or getattr(peer, 'chat_id', None) or getattr(peer, 'user_id', None) or getattr(peer, 'id', None)
        d = dialog_map.get(p_id)
        if d:
            entity = d.entity
            left = getattr(entity, 'left', False)
            kicked = getattr(entity, 'kicked', False)
            creator = getattr(entity, 'creator', False)
            admin_rights = getattr(entity, 'admin_rights', None)
            is_admin = False
            if not left and not kicked and (creator or admin_rights is not None):
                is_admin = True
            
            if is_admin:
                admin_channels.append((d.name, getattr(entity, 'username', 'N/A')))
            else:
                extra_channels.append((d.name, getattr(entity, 'username', 'N/A'), p_id))
        else:
            # Try fetching entity directly
            try:
                ent = await client.get_entity(peer)
                left = getattr(ent, 'left', False)
                kicked = getattr(ent, 'kicked', False)
                creator = getattr(ent, 'creator', False)
                admin_rights = getattr(ent, 'admin_rights', None)
                if not left and not kicked and (creator or admin_rights is not None):
                    admin_channels.append((getattr(ent, 'title', 'Channel'), getattr(ent, 'username', 'N/A')))
                else:
                    extra_channels.append((getattr(ent, 'title', 'Channel'), getattr(ent, 'username', 'N/A'), p_id))
            except Exception:
                extra_channels.append(("Unknown/Deleted Peer", "N/A", p_id))

    print(f"=== TOTAL ADMIN CHANNELS IN FOLDER: {len(admin_channels)} ===")
    print(f"=== EXTRA NON-ADMIN CHANNELS IN FOLDER: {len(extra_channels)} ===")
    for idx, (name, uname, p_id) in enumerate(extra_channels, 1):
        print(f"  [{idx:02d}] Name: {name} | Username: @{uname} | Peer ID: {p_id}")

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
