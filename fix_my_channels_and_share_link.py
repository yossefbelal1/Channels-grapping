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
    from telethon.tl.types import DialogFilter, InputChatlistDialogFilter, InputPeerSelf, TextWithEntities

    print("1. Fetching all dialogs (active + archived)...")
    dialogs_active = await client.get_dialogs(limit=None)
    dialogs_archived = []
    try:
        dialogs_archived = await client.get_dialogs(limit=None, folder=1)
    except Exception as e:
        print(f"Archived dialogs fetch note: {e}")

    all_dialogs = dialogs_active + dialogs_archived
    channels = [d for d in all_dialogs if d.is_channel or d.is_group]
    print(f"Total channels/groups found: {len(channels)}")

    admin_peers_map = {}
    admin_names = []

    for d in channels:
        entity = d.entity
        is_admin = False
        if not getattr(entity, 'left', False) and not getattr(entity, 'kicked', False) and not getattr(entity, 'deactivated', False):
            is_creator = getattr(entity, 'creator', False)
            admin_rights = getattr(entity, 'admin_rights', None)
            if is_creator:
                is_admin = True
            elif admin_rights is not None:
                # Ensure user has actual admin rights
                is_admin = True
        
        if is_admin:
            p_id = getattr(d.input_entity, 'channel_id', None) or getattr(d.input_entity, 'chat_id', None) or getattr(d.input_entity, 'user_id', None) or getattr(d.input_entity, 'id', None)
            if p_id:
                admin_peers_map[p_id] = d.input_entity
                admin_names.append(f"{d.name} (@{getattr(entity, 'username', 'N/A')})")

    print(f"\n2. Strictly detected {len(admin_peers_map)} ADMIN channels/groups:")
    for name in admin_names:
        print(f"   ✓ {name}")

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
        print(f"Found 'My_Channels' folder (ID: {my_channels_filter.id}). Updating include_peers and disabling default category flags...")
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
                    edit_res = await client(chatlists_fn.EditExportedInviteRequest(
                        chatlist=folder_input,
                        slug=slug,
                        peers=target_admin_peers
                    ))
                    print(f"  ✅ Share Link successfully updated! URL: {getattr(edit_res, 'url', url)}")
            else:
                print("  No share link exists yet. Exporting new chatlist invite link...")
                export_res = await client(chatlists_fn.ExportChatlistInviteRequest(
                    chatlist=folder_input,
                    title="My_Channels",
                    peers=target_admin_peers
                ))
                new_url = getattr(export_res, 'url', None) or getattr(getattr(export_res, 'invite', None), 'url', None)
                print(f"  ✅ New Share Link created! URL: {new_url}")
        except Exception as share_err:
            print(f"Share link error: {share_err}")
    else:
        print("'My_Channels' folder not found. Creating it now...")
        existing_ids = [f.id for f in all_filters if hasattr(f, 'id')]
        new_f_id = max(existing_ids) + 1 if existing_ids else 2
        new_filter = DialogFilter(
            id=new_f_id,
            title=TextWithEntities(text="My_Channels", entities=[]),
            pinned_peers=[],
            include_peers=target_admin_peers,
            exclude_peers=[],
            contacts=False,
            non_contacts=False,
            groups=False,
            broadcasts=False,
            bots=False
        )
        await client(messages_fn.UpdateDialogFilterRequest(id=new_f_id, filter=new_filter))
        print("Created 'My_Channels' folder!")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
