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
    import telethon.tl.functions.folders as folders_fn
    from telethon.tl.types import DialogFilter, TextWithEntities, InputFolderPeer

    print("=== STEP 1: FETCH ALL 71 VERIFIED ADMIN CHANNELS ===")
    d_active = await client.get_dialogs(limit=None)
    d_archived = []
    try:
        d_archived = await client.get_dialogs(limit=None, folder=1)
    except Exception:
        pass

    all_dialogs = d_active + d_archived
    seen_ids = set()
    admin_channels = []
    archived_unarch_peers = []

    archived_set = {d.id for d in d_archived}

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
                    seen_ids.add(cid)
                    admin_channels.append(d)
                    if cid in archived_set:
                        archived_unarch_peers.append(InputFolderPeer(peer=d.input_entity, folder_id=0))

    print(f"Total Verified Admin Channels: {len(admin_channels)}")

    # Un-archive any archived admin peers
    if archived_unarch_peers:
        try:
            await client(folders_fn.EditPeerFoldersRequest(folder_peers=archived_unarch_peers))
            print(f"✓ Un-archived {len(archived_unarch_peers)} admin peers.")
        except Exception as e:
            print(f"Unarchive note: {e}")

    print("\n=== STEP 2: CLEANUP DUPLICATE & SCATTERED FOLDERS ===")
    # Delete folder ID 126 (duplicate My_Channels)
    try:
        await client(messages_fn.UpdateDialogFilterRequest(id=126, filter=None))
        print("✓ Deleted duplicate folder ID 126 ('My_Channels').")
    except Exception:
        pass

    # Delete folder ID 122 clean reset
    try:
        await client(messages_fn.UpdateDialogFilterRequest(id=122, filter=None))
        print("✓ Reset folder ID 122.")
    except Exception:
        pass

    await asyncio.sleep(1)

    print("\n=== STEP 3: CREATE ONE CONSOLIDATED FOLDER 'My_Channels' ===")
    admin_peers_input = [d.input_entity for d in admin_channels]

    # Create master DialogFilter 122 with all 71 peers & broadcasts=True, groups=True
    master_filter = DialogFilter(
        id=122,
        title=TextWithEntities(text="My_Channels", entities=[]),
        pinned_peers=[],
        include_peers=admin_peers_input,
        exclude_peers=[],
        contacts=False,
        non_contacts=False,
        groups=True,
        broadcasts=True,
        bots=False,
        exclude_muted=False,
        exclude_read=False,
        exclude_archived=False
    )

    await client(messages_fn.UpdateDialogFilterRequest(id=122, filter=master_filter))
    print("✓ Successfully saved master consolidated DialogFilter 'My_Channels' (ID 122) on Telegram Server.")

    # Verification
    res_filters = await client(messages_fn.GetDialogFiltersRequest())
    print("\n🎉 TELEGRAM SERVER CONSOLIDATED FOLDER VERIFICATION:")
    for f in res_filters.filters:
        fid = getattr(f, 'id', None)
        title = getattr(f, 'title', '')
        if hasattr(title, 'text'):
            title = title.text
        if fid == 122 or title == 'My_Channels':
            inc = getattr(f, 'include_peers', [])
            print(f"   ✓ Folder ID {fid}: '{title}' | Broadcasts={getattr(f, 'broadcasts', False)} | Groups={getattr(f, 'groups', False)} | Peers Saved={len(inc)}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
