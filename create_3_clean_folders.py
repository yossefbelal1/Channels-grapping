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

    print("Fetching all verified admin channels...")
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
    print(f"Verified {total_peers} total admin peers.")

    # Split into 3 batches: 25, 25, 21
    part1 = admin_peers[0:25]
    part2 = admin_peers[25:50]
    part3 = admin_peers[50:]

    print(f"Folder 1 peers: {len(part1)}")
    print(f"Folder 2 peers: {len(part2)}")
    print(f"Folder 3 peers: {len(part3)}")

    # Delete existing folders 122, 123, 124
    for fid in [122, 123, 124]:
        try:
            await client(messages_fn.UpdateDialogFilterRequest(id=fid, filter=None))
        except Exception:
            pass

    await asyncio.sleep(1)

    # Folder 1 (ID 122): My_Channels 1
    f1 = DialogFilter(
        id=122,
        title=TextWithEntities(text="My_Channels 1", entities=[]),
        pinned_peers=[], include_peers=part1, exclude_peers=[],
        contacts=False, non_contacts=False, groups=False, broadcasts=False, bots=False,
        exclude_muted=False, exclude_read=False, exclude_archived=False
    )
    await client(messages_fn.UpdateDialogFilterRequest(id=122, filter=f1))
    print(f"✓ Created Folder 'My_Channels 1' (ID 122) with {len(part1)} channels.")

    # Folder 2 (ID 123): My_Channels 2
    f2 = DialogFilter(
        id=123,
        title=TextWithEntities(text="My_Channels 2", entities=[]),
        pinned_peers=[], include_peers=part2, exclude_peers=[],
        contacts=False, non_contacts=False, groups=False, broadcasts=False, bots=False,
        exclude_muted=False, exclude_read=False, exclude_archived=False
    )
    await client(messages_fn.UpdateDialogFilterRequest(id=123, filter=f2))
    print(f"✓ Created Folder 'My_Channels 2' (ID 123) with {len(part2)} channels.")

    # Folder 3 (ID 124): My_Channels 3
    f3 = DialogFilter(
        id=124,
        title=TextWithEntities(text="My_Channels 3", entities=[]),
        pinned_peers=[], include_peers=part3, exclude_peers=[],
        contacts=False, non_contacts=False, groups=False, broadcasts=False, bots=False,
        exclude_muted=False, exclude_read=False, exclude_archived=False
    )
    await client(messages_fn.UpdateDialogFilterRequest(id=124, filter=f3))
    print(f"✓ Created Folder 'My_Channels 3' (ID 124) with {len(part3)} channels.")

    # Verification
    res = await client(messages_fn.GetDialogFiltersRequest())
    print("\n🎉 TELEGRAM SERVER 3-FOLDER FINAL CONFIRMATION:")
    sum_saved = 0
    for f in res.filters:
        fid = getattr(f, 'id', None)
        title = getattr(f, 'title', '')
        if hasattr(title, 'text'):
            title = title.text
        if fid in (122, 123, 124) or 'My_Channels' in str(title):
            inc = getattr(f, 'include_peers', [])
            sum_saved += len(inc)
            print(f"   ✓ Folder ID {fid}: '{title}' -> {len(inc)} channels")

    print(f"\n🚀 TOTAL SAVED ACROSS 3 FOLDERS: {sum_saved} / {total_peers} CHANNELS!")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
