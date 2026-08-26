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
    import telethon.tl.functions.chatlists as chatlists_fn
    from telethon.tl.types import InputFolderPeer, InputChatlistDialogFilter, DialogFilter

    print("Fetching active and archived dialogs...")
    d_active = await client.get_dialogs(limit=None)
    d_archived = []
    try:
        d_archived = await client.get_dialogs(limit=None, folder=1)
    except Exception as e:
        print(f"Archived error: {e}")

    archived_set = {d.id for d in d_archived}
    all_dialogs = d_active + d_archived

    admin_channels = []
    archived_admin_peers = []
    seen_ids = set()

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
                    if cid in archived_set:
                        archived_admin_peers.append(InputFolderPeer(peer=d.input_entity, folder_id=0))

    print(f"\n--- EMPIRICAL FINDINGS ---")
    print(f"Total Admin Channels: {len(admin_channels)}")
    print(f"Admin Channels in Telegram Archive (folder=1): {len(archived_admin_peers)}")

    # Un-archive all archived admin peers to folder_id=0
    if archived_admin_peers:
        print(f"\nUn-archiving {len(archived_admin_peers)} admin channels so Telegram UI shows all {len(admin_channels)} in main folder...")
        # Process in batches of 50
        for i in range(0, len(archived_admin_peers), 50):
            batch = archived_admin_peers[i:i+50]
            try:
                await client(folders_fn.EditPeerFoldersRequest(folder_peers=batch))
                print(f"✓ Un-archived batch of {len(batch)} channels.")
            except Exception as unarch_err:
                print(f"Un-archive batch error: {unarch_err}")

    # Re-fetch all input peers after un-archiving
    admin_peers = [d.input_entity for d in admin_channels]

    # Update My_Channels Dialog Filter (ID 122)
    filters_res = await client(messages_fn.GetDialogFiltersRequest())
    my_filter = None
    for f in filters_res.filters:
        title = getattr(f, 'title', '')
        if hasattr(title, 'text'):
            title = title.text
        if title == 'My_Channels' or getattr(f, 'id', None) == 122:
            my_filter = f
            break

    if my_filter:
        new_filter = DialogFilter(
            id=my_filter.id,
            title=my_filter.title,
            pinned_peers=getattr(my_filter, 'pinned_peers', []),
            include_peers=admin_peers,
            exclude_peers=[],
            contacts=False,
            non_contacts=False,
            groups=False,
            broadcasts=False,
            bots=False,
            exclude_muted=False,
            exclude_read=False,
            exclude_archived=False
        )
        await client(messages_fn.UpdateDialogFilterRequest(id=my_filter.id, filter=new_filter))
        print(f"✓ Updated My_Channels Dialog Filter (ID {my_filter.id}) with exclude_archived=False and {len(admin_peers)} peers!")

    # Update Share Link
    try:
        folder_input = InputChatlistDialogFilter(filter_id=122)
        invite_res = await client(chatlists_fn.ExportChatlistInviteRequest(
            chatlist=folder_input,
            title="My_Channels",
            peers=admin_peers
        ))
        link_url = getattr(invite_res.invite, 'url', 'Updated')
        print(f"✓ Updated Chatlist Share Link: {link_url} (Contains {len(admin_peers)} admin peers)")
    except Exception as share_err:
        print(f"Share link update note: {share_err}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
