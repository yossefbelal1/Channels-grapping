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

    print("=== STEP 1: FETCH ALL DIALOGS (ACTIVE & ARCHIVED) ===")
    d_active = await client.get_dialogs(limit=None)
    d_archived = []
    try:
        d_archived = await client.get_dialogs(limit=None, folder=1)
    except Exception as e:
        print(f"Archived error: {e}")

    print(f"Active dialogs count: {len(d_active)}")
    print(f"Archived dialogs count: {len(d_archived)}")

    all_dialogs = d_active + d_archived
    seen_ids = set()

    channels_groups = []
    admin_channels = []

    for d in all_dialogs:
        if d.is_channel or d.is_group:
            cid = d.id
            if cid in seen_ids:
                continue
            seen_ids.add(cid)
            channels_groups.append(d)

            ent = d.entity
            left = getattr(ent, 'left', False)
            kicked = getattr(ent, 'kicked', False)
            deactivated = getattr(ent, 'deactivated', False)
            creator = getattr(ent, 'creator', False)
            admin_rights = getattr(ent, 'admin_rights', None)
            is_chat_admin = getattr(ent, 'admin', False)

            if not left and not kicked and not deactivated:
                if creator or admin_rights is not None or is_chat_admin:
                    admin_channels.append(d)

    print(f"\nTotal Channels & Groups Tamer is in: {len(channels_groups)}")
    print(f"Total Admin Channels & Groups: {len(admin_channels)}")

    print("\n=== STEP 2: INSPECT ALL TELEGRAM FOLDERS (DIALOG FILTERS) ===")
    res_filters = await client(messages_fn.GetDialogFiltersRequest())
    
    for f in res_filters.filters:
        fid = getattr(f, 'id', None)
        title = getattr(f, 'title', '')
        if hasattr(title, 'text'):
            title = title.text
        inc_peers = getattr(f, 'include_peers', [])
        exc_peers = getattr(f, 'exclude_peers', [])
        broadcasts = getattr(f, 'broadcasts', False)
        groups = getattr(f, 'groups', False)

        print(f"\n📁 Folder ID {fid}: '{title}'")
        print(f"   Include Peers Count: {len(inc_peers)}")
        print(f"   Exclude Peers Count: {len(exc_peers)}")
        print(f"   Broadcasts Flag: {broadcasts}, Groups Flag: {groups}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
