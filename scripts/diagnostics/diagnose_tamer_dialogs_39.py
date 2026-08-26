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

    print("Fetching active dialogs...")
    dialogs_active = await client.get_dialogs(limit=None)
    active_channels = [d for d in dialogs_active if d.is_channel or d.is_group]

    print("Fetching archived dialogs...")
    dialogs_archived = []
    try:
        dialogs_archived = await client.get_dialogs(limit=None, folder=1)
    except Exception as e:
        print(f"Archived fetch note: {e}")
    archived_channels = [d for d in dialogs_archived if d.is_channel or d.is_group]

    print(f"\n--- DIALOG STATS ---")
    print(f"Total Active Dialogs: {len(dialogs_active)}")
    print(f"Active Channels/Groups: {len(active_channels)}")
    print(f"Archived Channels/Groups: {len(archived_channels)}")

    # Admin check
    all_chans = active_channels + archived_channels
    admin_active = []
    admin_archived = []

    for d in all_chans:
        ent = d.entity
        left = getattr(ent, 'left', False)
        kicked = getattr(ent, 'kicked', False)
        deactivated = getattr(ent, 'deactivated', False)
        creator = getattr(ent, 'creator', False)
        admin_rights = getattr(ent, 'admin_rights', None)
        is_chat_admin = getattr(ent, 'admin', False)

        if not left and not kicked and not deactivated:
            if creator or admin_rights is not None or is_chat_admin:
                is_archived = d in archived_channels
                if is_archived:
                    admin_archived.append(d)
                else:
                    admin_active.append(d)

    print(f"\n--- ADMIN CHANNELS BREAKDOWN ---")
    print(f"Active Admin Channels/Groups: {len(admin_active)}")
    print(f"Archived Admin Channels/Groups: {len(admin_archived)}")
    print(f"Total Admin Channels/Groups: {len(admin_active) + len(admin_archived)}")

    print(f"\nList of Active Admin Channels/Groups ({len(admin_active)}):")
    for idx, d in enumerate(admin_active, 1):
        ent = d.entity
        print(f"  {idx}. '{d.name}' (@{getattr(ent, 'username', 'N/A')}) [id={d.id}]")

    if admin_archived:
        print(f"\nList of ARCHIVED Admin Channels/Groups ({len(admin_archived)}):")
        for idx, d in enumerate(admin_archived, 1):
            ent = d.entity
            print(f"  {idx}. [ARCHIVED] '{d.name}' (@{getattr(ent, 'username', 'N/A')}) [id={d.id}]")

    # Check Telegram Dialog Filters (Folders)
    print(f"\n--- TELEGRAM FOLDERS CHECK ---")
    filters = await client(messages_fn.GetDialogFiltersRequest())
    my_folder = None
    for f in filters:
        title = getattr(f, 'title', '')
        if hasattr(title, 'text'):
            title = title.text
        if title == 'My_Channels' or getattr(f, 'id', None) == 122:
            my_folder = f
            print(f"Found Folder: ID={f.id}, Title='{title}'")
            include_peers = getattr(f, 'include_peers', [])
            print(f"Include Peers count in folder: {len(include_peers)}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
