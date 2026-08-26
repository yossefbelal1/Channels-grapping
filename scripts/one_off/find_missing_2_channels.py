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
    from telethon.tl.types import InputChatlistDialogFilter, DialogFilterChatlist, DialogFilter

    dialogs_active = await client.get_dialogs(limit=None)
    dialogs_archived = await client.get_dialogs(limit=None, folder=1)
    all_dialogs = dialogs_active + dialogs_archived
    channels = [d for d in all_dialogs if d.is_channel or d.is_group]

    admin_dialogs_dict = {}
    for d in channels:
        entity = d.entity
        is_admin = False
        if not getattr(entity, 'left', False) and not getattr(entity, 'kicked', False) and not getattr(entity, 'deactivated', False):
            if getattr(entity, 'creator', False) or getattr(entity, 'admin_rights', None) is not None:
                is_admin = True
        if is_admin:
            p_id = getattr(d.input_entity, 'channel_id', None) or getattr(d.input_entity, 'chat_id', None) or getattr(d.input_entity, 'user_id', None) or getattr(d.input_entity, 'id', None)
            if p_id:
                admin_dialogs_dict[p_id] = d

    print(f"Total Admin Dialogs detected: {len(admin_dialogs_dict)}")

    res_filters = await client(messages_fn.GetDialogFiltersRequest())
    all_filters = res_filters.filters if hasattr(res_filters, 'filters') else []

    my_filter = None
    for f in all_filters:
        if hasattr(f, 'title') and f.title:
            t = f.title.text if hasattr(f.title, 'text') else str(f.title)
            if t == "My_Channels":
                my_filter = f
                break

    if my_filter:
        included_ids = set()
        for p in getattr(my_filter, 'include_peers', []):
            pid = getattr(p, 'channel_id', None) or getattr(p, 'chat_id', None) or getattr(p, 'id', None)
            if pid:
                included_ids.add(pid)

        print(f"IDs in My_Channels filter include_peers: {len(included_ids)}")

        missing_ids = set(admin_dialogs_dict.keys()) - included_ids
        print(f"\n--- MISSING {len(missing_ids)} Admin Channel(s) from My_Channels ---")
        for m_id in missing_ids:
            d = admin_dialogs_dict[m_id]
            print(f"  Missing: '{d.name}' (@{getattr(d.entity, 'username', 'N/A')}) | ID: {m_id} | InputPeer: {type(d.input_entity)}")

        # FORCE ADD ALL 70 ADMIN CHANNELS
        all_admin_peers = [d.input_entity for d in admin_dialogs_dict.values()]
        print(f"\nUpdating My_Channels folder with ALL {len(all_admin_peers)} admin peers...")
        my_filter.include_peers = all_admin_peers
        my_filter.exclude_peers = []
        if hasattr(my_filter, 'groups'): my_filter.groups = False
        if hasattr(my_filter, 'broadcasts'): my_filter.broadcasts = False
        if hasattr(my_filter, 'contacts'): my_filter.contacts = False
        if hasattr(my_filter, 'non_contacts'): my_filter.non_contacts = False
        if hasattr(my_filter, 'bots'): my_filter.bots = False

        await client(messages_fn.UpdateDialogFilterRequest(id=my_filter.id, filter=my_filter))
        print("Updated My_Channels filter on Telegram!")

        # Update Share Link
        folder_input = InputChatlistDialogFilter(filter_id=my_filter.id)
        exp_res = await client(chatlists_fn.GetExportedInvitesRequest(chatlist=folder_input))
        invites = getattr(exp_res, 'invites', [])
        for inv in invites:
            slug = inv.url.split('/')[-1] if '/' in inv.url else inv.url
            print(f"Updating share link slug {slug} with ALL {len(all_admin_peers)} peers...")
            await client(chatlists_fn.EditExportedInviteRequest(chatlist=folder_input, slug=slug, peers=all_admin_peers))
            print(f"Share link updated successfully! URL: {inv.url}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
