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
    active_ids = {d.id: d for d in dialogs_active}

    print("Fetching archived dialogs...")
    dialogs_archived = []
    try:
        dialogs_archived = await client.get_dialogs(limit=None, folder=1)
    except Exception as e:
        print(f"Archived fetch note: {e}")
    archived_ids = {d.id: d for d in dialogs_archived}

    all_dialogs = dialogs_active + dialogs_archived
    channels = [d for d in all_dialogs if d.is_channel or d.is_group]

    admin_channels = []
    for d in channels:
        ent = d.entity
        left = getattr(ent, 'left', False)
        kicked = getattr(ent, 'kicked', False)
        deactivated = getattr(ent, 'deactivated', False)
        creator = getattr(ent, 'creator', False)
        admin_rights = getattr(ent, 'admin_rights', None)
        is_chat_admin = getattr(ent, 'admin', False)

        if not left and not kicked and not deactivated:
            if creator or admin_rights is not None or is_chat_admin:
                is_archived = d.id in archived_ids
                admin_channels.append((d.name, getattr(ent, 'username', 'N/A'), d.id, is_archived, d))

    print(f"\nTotal Detected Admin Channels: {len(admin_channels)}")
    print(f"Active (non-archived) Admin Channels: {sum(1 for x in admin_channels if not x[3])}")
    print(f"Archived Admin Channels: {sum(1 for x in admin_channels if x[3])}")

    for idx, (name, uname, cid, is_arch, d) in enumerate(admin_channels, 1):
        arch_str = "[ARCHIVED]" if is_arch else "[ACTIVE]"
        print(f"{idx}. {arch_str} {name} (@{uname}) [id={cid}]")

    # If any admin channel is archived, let's unarchive it so it appears in the active dialog list!
    archived_admin_dialogs = [d for (name, uname, cid, is_arch, d) in admin_channels if is_arch]
    if archived_admin_dialogs:
        print(f"\nUn-archiving {len(archived_admin_dialogs)} admin channels so they all show up in main chat list & folder count...")
        for d in archived_admin_dialogs:
            try:
                await client(messages_fn.EditFolderRequest(folder_id=0, peers=[d.input_entity]))
                print(f"  ✓ Un-archived: {d.name}")
            except Exception as unarch_err:
                print(f"  Failed to un-archive {d.name}: {unarch_err}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
