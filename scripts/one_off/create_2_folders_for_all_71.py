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
    from telethon.tl.types import DialogFilter, TextWithEntities

    print("Fetching all admin channels...")
    d_active = await client.get_dialogs(limit=None)
    d_archived = []
    try:
        d_archived = await client.get_dialogs(limit=None, folder=1)
    except Exception:
        pass

    all_dialogs = d_active + d_archived
    seen_ids = set()
    admin_channels = []

    for d in all_dialogs:
        if d.is_channel or d.is_group:
            cid = d.id
            if cid in seen_ids:
                continue
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
                    seen_ids.add(cid)

    admin_peers = [d.input_entity for d in admin_channels]
    total_peers = len(admin_peers)
    print(f"Total verified admin channels: {total_peers}")

    # Split into 2 parts: part 1 (39), part 2 (32)
    part1_peers = admin_peers[:39]
    part2_peers = admin_peers[39:]

    print(f"Part 1 peers: {len(part1_peers)}")
    print(f"Part 2 peers: {len(part2_peers)}")

    # 1. Update Folder 1 (ID 122) -> My_Channels 1
    filter1 = DialogFilter(
        id=122,
        title=TextWithEntities(text="My_Channels 1", entities=[]),
        pinned_peers=[],
        include_peers=part1_peers,
        exclude_peers=[],
        contacts=False, non_contacts=False, groups=False, broadcasts=False, bots=False,
        exclude_muted=False, exclude_read=False, exclude_archived=False
    )
    await client(messages_fn.UpdateDialogFilterRequest(id=122, filter=filter1))
    print(f"✓ Created Folder 'My_Channels 1' (ID 122) with {len(part1_peers)} channels.")

    # 2. Update Folder 2 (ID 123) -> My_Channels 2
    filter2 = DialogFilter(
        id=123,
        title=TextWithEntities(text="My_Channels 2", entities=[]),
        pinned_peers=[],
        include_peers=part2_peers,
        exclude_peers=[],
        contacts=False, non_contacts=False, groups=False, broadcasts=False, bots=False,
        exclude_muted=False, exclude_read=False, exclude_archived=False
    )
    await client(messages_fn.UpdateDialogFilterRequest(id=123, filter=filter2))
    print(f"✓ Created Folder 'My_Channels 2' (ID 123) with {len(part2_peers)} channels.")

    # Confirm
    res = await client(messages_fn.GetDialogFiltersRequest())
    print("\n🎉 TELEGRAM SERVER 2-FOLDER CONFIRMATION:")
    for f in res.filters:
        fid = getattr(f, 'id', None)
        title = getattr(f, 'title', '')
        if hasattr(title, 'text'):
            title = title.text
        if fid in (122, 123) or 'My_Channels' in str(title):
            inc = getattr(f, 'include_peers', [])
            print(f"   Folder ID {fid}: '{title}' -> Saved {len(inc)} channels")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
