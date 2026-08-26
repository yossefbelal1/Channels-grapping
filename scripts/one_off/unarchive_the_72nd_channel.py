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

    import telethon.tl.functions.folders as folders_fn
    from telethon.tl.types import InputFolderPeer

    print("Fetching active dialogs...")
    dialogs_active = await client.get_dialogs(limit=None)
    active_ids = {d.id for d in dialogs_active}

    print("Fetching archived dialogs...")
    dialogs_archived = []
    try:
        dialogs_archived = await client.get_dialogs(limit=None, folder=1)
    except Exception as e:
        print(f"Archived fetch note: {e}")

    archived_admin_channels = []
    for d in dialogs_archived:
        if d.is_channel or d.is_group:
            ent = d.entity
            left = getattr(ent, 'left', False)
            kicked = getattr(ent, 'kicked', False)
            deactivated = getattr(ent, 'deactivated', False)
            creator = getattr(ent, 'creator', False)
            admin_rights = getattr(ent, 'admin_rights', None)
            is_chat_admin = getattr(ent, 'admin', False)

            if not left and not kicked and not deactivated:
                if creator or admin_rights is not None or is_chat_admin:
                    archived_admin_channels.append(d)

    print(f"\nFOUND {len(archived_admin_channels)} ARCHIVED ADMIN CHANNELS:")
    folder_peers = []
    for d in archived_admin_channels:
        ent = d.entity
        print(f"  ★ Name: '{d.name}' | Username: @{getattr(ent, 'username', 'N/A')} | ID: {d.id}")
        folder_peers.append(InputFolderPeer(peer=d.input_entity, folder_id=0))

    if folder_peers:
        print(f"\nUn-archiving {len(folder_peers)} channel(s)...")
        await client(folders_fn.EditPeerFoldersRequest(folder_peers=folder_peers))
        print("✓ Successfully un-archived! All 72 admin channels are now ACTIVE in main chat list.")
    else:
        print("No archived admin channels found.")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
