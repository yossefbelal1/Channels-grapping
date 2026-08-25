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
    from telethon.tl.types import DialogFilter, InputPeerChannel, InputPeerChat, InputChatlistDialogFilter

    print("Fetching active dialogs...")
    dialogs_active = await client.get_dialogs(limit=None)
    dialogs_archived = []
    try:
        dialogs_archived = await client.get_dialogs(limit=None, folder=1)
    except Exception:
        pass

    all_dialogs = dialogs_active + dialogs_archived
    channels = [d for d in all_dialogs if d.is_channel or d.is_group]

    admin_dialogs = []
    seen_ids = set()

    for d in channels:
        ent = d.entity
        p_id = getattr(d.input_entity, 'channel_id', None) or getattr(d.input_entity, 'chat_id', None) or getattr(d.input_entity, 'id', None)
        if p_id in seen_ids:
            continue
        
        left = getattr(ent, 'left', False)
        kicked = getattr(ent, 'kicked', False)
        deactivated = getattr(ent, 'deactivated', False)
        creator = getattr(ent, 'creator', False)
        admin_rights = getattr(ent, 'admin_rights', None)

        if not left and not kicked and not deactivated:
            if creator or admin_rights is not None or getattr(ent, 'admin', False):
                seen_ids.add(p_id)
                admin_dialogs.append(d)

    print(f"\nTotal strictly verified ADMIN channels & groups found: {len(admin_dialogs)}")

    # Fetch existing filters
    res_filters = await client(messages_fn.GetDialogFiltersRequest())
    all_filters = res_filters.filters if hasattr(res_filters, 'filters') else []

    my_filter_id = 2 # Default folder ID
    for f in all_filters:
        if hasattr(f, 'title') and f.title:
            t = f.title.text if hasattr(f.title, 'text') else str(f.title)
            if t == "My_Channels":
                my_filter_id = f.id
                break

    # Build include_peers list
    include_peers = []
    for d in admin_dialogs:
        include_peers.append(d.input_entity)

    # Create / Update My_Channels DialogFilter
    updated_filter = DialogFilter(
        id=my_filter_id,
        title="My_Channels",
        pinned_peers=[],
        include_peers=include_peers,
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

    print(f"\nUpdating 'My_Channels' folder filter with ID {my_filter_id} for {len(include_peers)} peers...")
    await client(messages_fn.UpdateDialogFilterRequest(id=my_filter_id, filter=updated_filter))
    print("Folder filter updated successfully!")

    # Export / Update Shareable Folder Link
    folder_input = InputChatlistDialogFilter(filter_id=my_filter_id)
    exp_res = await client(chatlists_fn.GetExportedInvitesRequest(chatlist=folder_input))
    invites = getattr(exp_res, 'invites', [])

    share_url = "https://t.me/addlist/4vQwb-CbnO03MDY0"
    target_invite = None
    for inv in invites:
        if inv.url == share_url or "4vQwb-CbnO03MDY0" in inv.url:
            target_invite = inv
            break
            
    if not target_invite and invites:
        target_invite = invites[0]

    if target_invite:
        print(f"\nSyncing shareable invite link ({target_invite.url}) with {len(include_peers)} admin peers...")
        edit_res = await client(chatlists_fn.EditExportedInviteRequest(
            chatlist=folder_input,
            slug=target_invite.slug,
            title="My_Channels",
            peers=include_peers
        ))
        print(f"Share link updated successfully! Final URL: {edit_res.invite.url}")
    else:
        print("Creating new exported invite share link...")
        new_inv = await client(chatlists_fn.ExportChatlistInviteRequest(
            chatlist=folder_input,
            title="My_Channels",
            peers=include_peers
        ))
        print(f"New share link created: {new_inv.invite.url}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
