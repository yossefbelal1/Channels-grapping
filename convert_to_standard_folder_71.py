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

    print("Fetching all active and archived admin channels...")
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

    admin_peers_all = [d.input_entity for d in admin_channels]
    print(f"Found {len(admin_peers_all)} verified admin peers.")

    # 1. Delete exported chatlist invites for folder ID 122 if any exist
    try:
        invites_res = await client(chatlists_fn.GetExportedInvitesRequest(chatlist=InputChatlistDialogFilter(filter_id=122)))
        invites = getattr(invites_res, 'invites', [])
        for inv in invites:
            slug = getattr(inv, 'slug', None) or getattr(getattr(inv, 'invite', None), 'slug', None)
            if slug:
                await client(chatlists_fn.DeleteExportedInviteRequest(chatlist=InputChatlistDialogFilter(filter_id=122), slug=slug))
                print(f"✓ Deleted Chatlist Share Link '{slug}' to convert folder 122 into a STANDARD folder.")
    except Exception as inv_err:
        print(f"Chatlist delete note: {inv_err}")

    # 2. Delete existing folder 122 to reset filter type
    try:
        await client(messages_fn.UpdateDialogFilterRequest(id=122, filter=None))
        print("✓ Reset folder ID 122 on Telegram server.")
        await asyncio.sleep(1)
    except Exception:
        pass

    # 3. Create PURE STANDARD DialogFilter (Non-Shareable) with all 71 peers
    standard_filter = DialogFilter(
        id=122,
        title=TextWithEntities(text="My_Channels", entities=[]),
        pinned_peers=[],
        include_peers=admin_peers_all,
        exclude_peers=[],
        contacts=False, non_contacts=False, groups=False, broadcasts=False, bots=False,
        exclude_muted=False, exclude_read=False, exclude_archived=False
    )

    await client(messages_fn.UpdateDialogFilterRequest(id=122, filter=standard_filter))
    print(f"✓ Successfully created PURE STANDARD Telegram Folder 'My_Channels' (ID 122) with ALL {len(admin_peers_all)} admin channels!")

    # 4. Verify peers in folder ID 122
    filters_check = await client(messages_fn.GetDialogFiltersRequest())
    for f in filters_check.filters:
        fid = getattr(f, 'id', None)
        title = getattr(f, 'title', '')
        if hasattr(title, 'text'):
            title = title.text
        if fid == 122 or title == 'My_Channels':
            inc_peers = getattr(f, 'include_peers', [])
            print(f"\n🎉 TELEGRAM SERVER CONFIRMATION:")
            print(f"   Folder ID: {fid}")
            print(f"   Folder Name: '{title}'")
            print(f"   Total Channels/Peers in Folder: {len(inc_peers)} / 71")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
