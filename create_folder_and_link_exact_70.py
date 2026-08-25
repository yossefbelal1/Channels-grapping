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

    admin_peers_all = [d.input_entity for d in admin_channels]
    print(f"\nTotal Admin Peers to include: {len(admin_peers_all)}")

    # Delete ID 122 if present
    try:
        await client(messages_fn.UpdateDialogFilterRequest(id=122, filter=None))
        print("✓ Deleted folder 122 to force clean recreation.")
    except Exception:
        pass

    # Create fresh DialogFilter
    fresh_filter = DialogFilter(
        id=122,
        title=TextWithEntities(text="My_Channels", entities=[]),
        pinned_peers=[],
        include_peers=admin_peers_all,
        exclude_peers=[],
        contacts=False, non_contacts=False, groups=False, broadcasts=False, bots=False,
        exclude_muted=False, exclude_read=False, exclude_archived=False
    )
    await client(messages_fn.UpdateDialogFilterRequest(id=122, filter=fresh_filter))
    print(f"✓ Created Folder 'My_Channels' (ID 122) with all {len(admin_peers_all)} admin channels!")

    # Export Chatlist Link
    folder_input = InputChatlistDialogFilter(filter_id=122)
    share_link = None
    try:
        invite_res = await client(chatlists_fn.ExportChatlistInviteRequest(
            chatlist=folder_input,
            title="My_Channels",
            peers=admin_peers_all
        ))
        share_link = getattr(invite_res.invite, 'url', None)
        print(f"✓ Generated Exported Share Link: {share_link}")
    except Exception as ex:
        print(f"Share link creation note: {ex}")

    # Check Link Invite Details via CheckChatlistInviteRequest
    if share_link:
        try:
            slug = share_link.split('/')[-1].replace('+', '')
            check_res = await client(chatlists_fn.CheckChatlistInviteRequest(slug=slug))
            chats = getattr(check_res, 'chats', [])
            already_chats = getattr(check_res, 'already_peers', [])
            print(f"\n--- TELEGRAM INVITE LINK CHECK ---")
            print(f"🔗 Link URL: {share_link}")
            print(f"📊 Telegram Link Internal Chats Count: {len(chats)}")
        except Exception as check_ex:
            print(f"Check chatlist note: {check_ex}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
