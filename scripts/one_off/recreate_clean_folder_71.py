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
    import telethon.tl.functions.chatlists as chatlists_fn
    from telethon.tl.types import DialogFilter, TextWithEntities, InputChatlistDialogFilter

    print("Fetching active and archived dialogs...")
    d_active = await client.get_dialogs(limit=None)
    d_archived = []
    try:
        d_archived = await client.get_dialogs(limit=None, folder=1)
    except Exception as e:
        print(f"Archived error: {e}")

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
    print(f"Strictly verified {len(admin_peers)} admin peers.")

    # 1. Fetch current filters
    filters_res = await client(messages_fn.GetDialogFiltersRequest())
    existing_filter = None
    target_id = 122

    for f in filters_res.filters:
        title = getattr(f, 'title', '')
        if hasattr(title, 'text'):
            title = title.text
        if title == 'My_Channels' or getattr(f, 'id', None) == 122:
            existing_filter = f
            target_id = getattr(f, 'id', 122)
            break

    # 2. Delete existing folder to clear stale cache
    if existing_filter:
        try:
            await client(messages_fn.UpdateDialogFilterRequest(id=target_id, filter=None))
            print(f"✓ Removed old folder ID {target_id} from Telegram server to clear stale device cache.")
            await asyncio.sleep(1)
        except Exception as del_err:
            print(f"Delete folder note: {del_err}")

    # 3. Create fresh new DialogFilter with ID 122 containing all 71 peers
    clean_filter = DialogFilter(
        id=target_id,
        title=TextWithEntities(text="My_Channels", entities=[]),
        pinned_peers=[],
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

    await client(messages_fn.UpdateDialogFilterRequest(id=target_id, filter=clean_filter))
    print(f"✓ Created fresh 'My_Channels' folder (ID {target_id}) on Telegram server with all {len(admin_peers)} peers!")

    # 4. Generate Exported Share Link
    try:
        folder_input = InputChatlistDialogFilter(filter_id=target_id)
        invite_res = await client(chatlists_fn.ExportChatlistInviteRequest(
            chatlist=folder_input,
            title="My_Channels",
            peers=admin_peers
        ))
        link_url = getattr(invite_res.invite, 'url', 'Updated')
        print(f"✓ Exported Fresh Share Link: {link_url} (Contains {len(admin_peers)} admin peers)")
    except Exception as share_err:
        print(f"Share link export note: {share_err}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
