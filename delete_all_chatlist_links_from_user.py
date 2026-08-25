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

    print("Deleting all active Chatlist Share Links from Telegram Server...")

    # Fetch all dialog filters
    res_filters = await client(messages_fn.GetDialogFiltersRequest())
    
    for f in res_filters.filters:
        fid = getattr(f, 'id', None)
        title = getattr(f, 'title', '')
        if hasattr(title, 'text'):
            title = title.text
        
        if fid:
            try:
                invites_res = await client(chatlists_fn.GetExportedInvitesRequest(chatlist=InputChatlistDialogFilter(filter_id=fid)))
                invites = getattr(invites_res, 'invites', [])
                for inv in invites:
                    slug = getattr(inv, 'slug', None) or getattr(getattr(inv, 'invite', None), 'slug', None)
                    if slug:
                        await client(chatlists_fn.DeleteExportedInviteRequest(chatlist=InputChatlistDialogFilter(filter_id=fid), slug=slug))
                        print(f"✓ Deleted Chatlist Link '{slug}' from Folder ID {fid} ('{title}').")
            except Exception as e:
                pass

    print("\nFetching all admin channels to rebuild standard folder...")
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

    admin_peers_all = [d.input_entity for d in admin_channels]
    print(f"Total Verified Admin Peers: {len(admin_peers_all)}")

    # Update My_Channels as pure standard folder
    clean_std_filter = DialogFilter(
        id=122,
        title=TextWithEntities(text="My_Channels", entities=[]),
        pinned_peers=[],
        include_peers=admin_peers_all,
        exclude_peers=[],
        contacts=False, non_contacts=False, groups=False, broadcasts=False, bots=False,
        exclude_muted=False, exclude_read=False, exclude_archived=False
    )
    await client(messages_fn.UpdateDialogFilterRequest(id=122, filter=clean_std_filter))
    print("✓ Successfully updated 'My_Channels' (ID 122) as a PURE Standard Folder on Telegram Server.")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
