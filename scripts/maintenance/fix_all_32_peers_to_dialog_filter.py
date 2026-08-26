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
    import telethon.tl.functions.messages as messages_fn
    from telethon.tl.types import InputFolderPeer, DialogFilter, TextWithEntities

    print("Fetching active and archived dialogs...")
    d_active = await client.get_dialogs(limit=None)
    d_archived = []
    try:
        d_archived = await client.get_dialogs(limit=None, folder=1)
    except Exception as e:
        print(f"Archived error: {e}")

    archived_set = {d.id for d in d_archived}
    all_dialogs = d_active + d_archived
    seen_ids = set()

    all_admin_dialogs = []
    archived_admin_peers = []

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
                    all_admin_dialogs.append(d)
                    if cid in archived_set:
                        archived_admin_peers.append(InputFolderPeer(peer=d.input_entity, folder_id=0))

    print(f"Total Verified Admin Dialogs: {len(all_admin_dialogs)}")
    print(f"Archived Admin Peers to un-archive: {len(archived_admin_peers)}")

    # 1. Un-archive all archived admin peers so Telegram allows adding them to folders
    if archived_admin_peers:
        for i in range(0, len(archived_admin_peers), 50):
            batch = archived_admin_peers[i:i+50]
            try:
                await client(folders_fn.EditPeerFoldersRequest(folder_peers=batch))
                print(f"✓ Un-archived {len(batch)} admin peers to main folder_id=0.")
            except Exception as unarch_err:
                print(f"Unarchive error: {unarch_err}")

    # 2. Re-fetch dialogs list after un-archiving to refresh Telethon input_peer entities
    print("Re-fetching dialogs list after un-archiving...")
    refreshed_dialogs = await client.get_dialogs(limit=None)
    refreshed_admin_peers = []
    seen_refreshed = set()

    for d in refreshed_dialogs:
        if d.is_channel or d.is_group:
            cid = d.id
            if cid in seen_refreshed:
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
                    seen_refreshed.add(cid)
                    refreshed_admin_peers.append(d.input_entity)

    print(f"Refreshed Admin Input Peers Count: {len(refreshed_admin_peers)}")

    # 3. Update DialogFilter ID 122 with refreshed input peers
    filter_122 = DialogFilter(
        id=122,
        title=TextWithEntities(text="My_Channels", entities=[]),
        pinned_peers=[],
        include_peers=refreshed_admin_peers,
        exclude_peers=[],
        contacts=False, non_contacts=False, groups=False, broadcasts=False, bots=False,
        exclude_muted=False, exclude_read=False, exclude_archived=False
    )

    await client(messages_fn.UpdateDialogFilterRequest(id=122, filter=filter_122))
    print("✓ Sent UpdateDialogFilterRequest(id=122) to Telegram server.")

    # 4. Verify Telegram Server Filter count
    res_filters = await client(messages_fn.GetDialogFiltersRequest())
    saved_filter = None
    for f in res_filters.filters:
        if getattr(f, 'id', None) == 122:
            saved_filter = f
            break

    inc_peers = getattr(saved_filter, 'include_peers', []) if saved_filter else []
    print(f"\n🎉 TELEGRAM SERVER FINAL CONFIRMATION:")
    print(f"   Saved Folder ID: {getattr(saved_filter, 'id', 'N/A')}")
    print(f"   Total Admin Peers Saved in Telegram Server Filter: {len(inc_peers)} / {len(refreshed_admin_peers)}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
