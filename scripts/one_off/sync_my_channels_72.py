import asyncio
import os
import sys
import logging
from telethon import TelegramClient

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from tg_manager import get_session_path

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

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
    from telethon.tl.types import InputChatlistDialogFilter, InputPeerSelf

    print("1. Fetching all dialogs (active + archived)...")
    dialogs_active = await client.get_dialogs(limit=None)
    dialogs_archived = []
    try:
        dialogs_archived = await client.get_dialogs(limit=None, folder=1)
    except Exception as e:
        print(f"Archived dialogs fetch note: {e}")

    all_dialogs = dialogs_active + dialogs_archived
    channels = [d for d in all_dialogs if d.is_channel or d.is_group]

    admin_peers_map = {}
    admin_names = []

    for d in channels:
        entity = d.entity
        is_admin = False
        if not getattr(entity, 'left', False) and not getattr(entity, 'kicked', False) and not getattr(entity, 'deactivated', False):
            is_creator = getattr(entity, 'creator', False)
            admin_rights = getattr(entity, 'admin_rights', None)
            is_chat_admin = getattr(entity, 'admin', False)
            if is_creator or admin_rights is not None or is_chat_admin:
                is_admin = True
        
        if is_admin:
            p_id = getattr(d.input_entity, 'channel_id', None) or getattr(d.input_entity, 'chat_id', None) or getattr(d.input_entity, 'user_id', None) or getattr(d.input_entity, 'id', None)
            if p_id and p_id not in admin_peers_map:
                admin_peers_map[p_id] = d.input_entity
                admin_names.append(f"{d.name} (@{getattr(entity, 'username', 'N/A')})")

    print(f"\n2. Strictly detected {len(admin_peers_map)} ADMIN channels/groups:")
    for idx, name in enumerate(admin_names, 1):
        print(f"   {idx}. {name}")

    target_admin_peers = list(admin_peers_map.values()) if admin_peers_map else [InputPeerSelf()]

    print("\n3. Fetching Dialog Filters (Folders)...")
    res_filters = await client(messages_fn.GetDialogFiltersRequest())
    all_filters = res_filters.filters if hasattr(res_filters, 'filters') else []

    my_channels_filter = None
    for f in all_filters:
        if hasattr(f, 'title') and f.title:
            title_text = f.title.text if hasattr(f.title, 'text') else str(f.title)
            if title_text == "My_Channels":
                my_channels_filter = f
                break

    if my_channels_filter:
        print(f"Found 'My_Channels' folder (ID: {my_channels_filter.id}). Updating include_peers to {len(target_admin_peers)} admin peers...")
        my_channels_filter.include_peers = target_admin_peers
        my_channels_filter.exclude_peers = []
        my_channels_filter.contacts = False
        my_channels_filter.non_contacts = False
        my_channels_filter.groups = False
        my_channels_filter.broadcasts = False
        my_channels_filter.bots = False

        await client(messages_fn.UpdateDialogFilterRequest(id=my_channels_filter.id, filter=my_channels_filter))
        print("Successfully updated 'My_Channels' folder on Telegram server!")

        # 4. Update or Export Chatlist Share Link
        print("\n4. Updating Chatlist Share Link for 'My_Channels'...")
        folder_input = InputChatlistDialogFilter(filter_id=my_channels_filter.id)
        try:
            exp_res = await client(chatlists_fn.GetExportedInvitesRequest(chatlist=folder_input))
            invites = getattr(exp_res, 'invites', [])
            if invites:
                for inv in invites:
                    url = getattr(inv, 'url', '')
                    slug = url.split('/')[-1] if '/' in url else url
                    print(f"  Updating existing share link: {url} (slug: {slug}) with {len(target_admin_peers)} admin peers...")
                    title_str = "My_Channels"
                    edit_res = await client(chatlists_fn.EditExportedInviteRequest(
                        chatlist=folder_input,
                        slug=slug,
                        title=title_str,
                        peers=target_admin_peers
                    ))
                    inv_url = getattr(edit_res, 'url', None) or (getattr(edit_res.invite, 'url', None) if hasattr(edit_res, 'invite') else url)
                    print(f"  ✓ Share link successfully updated: {inv_url} (contains {len(target_admin_peers)} admin channels/groups)")
            else:
                print("  No existing share link found. Creating new exported invite link...")
                new_inv = await client(chatlists_fn.ExportChatlistInviteRequest(
                    chatlist=folder_input,
                    title="My_Channels",
                    peers=target_admin_peers
                ))
                inv_url = getattr(new_inv, 'url', None) or (getattr(new_inv.invite, 'url', None) if hasattr(new_inv, 'invite') else "")
                print(f"  ✓ Created share link: {inv_url}")
        except Exception as e_share:
            print(f"  Error updating chatlist share link: {e_share}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
