import asyncio
import os
import sys
from telethon import TelegramClient

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from tg_manager import get_session_path

async def main():
    session_path = get_session_path("user_session")
    print(f"Using session path: {session_path}")
    client = TelegramClient(session_path, 36318125, '5f2ea025376141a257979750c3fc9cf7')
    await client.connect()
    if not await client.is_user_authorized():
        print("user_session NOT authorized!")
        await client.disconnect()
        return

    import telethon.tl.functions.chatlists as chatlists_fn
    import telethon.tl.functions.messages as messages_fn
    from telethon.tl.types import DialogFilter, InputChatlistDialogFilter

    print("\n--- Telethon chatlists functions ---")
    print([attr for attr in dir(chatlists_fn) if not attr.startswith('_')])

    print("\n--- Dialog Filters ---")
    res_filters = await client(messages_fn.GetDialogFiltersRequest())
    filters = res_filters.filters if hasattr(res_filters, 'filters') else []

    my_channels_filter = None
    for f in filters:
        title = f.title.text if hasattr(f.title, 'text') else str(getattr(f, 'title', ''))
        print(f"Folder ID {getattr(f, 'id', None)}: '{title}' - include_peers: {len(getattr(f, 'include_peers', []))}")
        if title == "My_Channels":
            my_channels_filter = f

    if my_channels_filter:
        print(f"\n--- Checking My_Channels (ID: {my_channels_filter.id}) peers ---")
        dialogs_active = await client.get_dialogs(limit=None)
        dialogs_archived = await client.get_dialogs(limit=None, folder=1)
        all_dialogs = dialogs_active + dialogs_archived

        for p in my_channels_filter.include_peers:
            p_id = getattr(p, 'channel_id', None) or getattr(p, 'chat_id', None) or getattr(p, 'id', None)
            d_match = next((d for d in all_dialogs if getattr(d.entity, 'id', None) == p_id), None)
            if d_match:
                ent = d_match.entity
                # Strict admin check: creator or admin_rights is not None
                is_creator = getattr(ent, 'creator', False)
                admin_rights = getattr(ent, 'admin_rights', None)
                is_admin = is_creator or (admin_rights is not None)
                print(f"  [{'ADMIN' if is_admin else 'NOT_ADMIN'}] {d_match.name} (@{getattr(ent, 'username', 'N/A')}) | creator={is_creator} | admin_rights={admin_rights}")
            else:
                print(f"  [UNKNOWN PEER] p_id={p_id}")

        # Check chatlist share link (Invite link)
        print("\n--- Checking Chatlist Invites (Share Link) ---")
        try:
            dialog_filter_input = InputChatlistDialogFilter(filter_id=my_channels_filter.id)
            invites = await client(chatlists_fn.GetExportedInvitesRequest(chatlist=dialog_filter_input))
            print(f"Exported Invites: {invites}")
            if hasattr(invites, 'invites') and invites.invites:
                for inv in invites.invites:
                    print(f"  Share Link URL: {inv.url} | Peers count: {len(inv.peers)}")
        except Exception as e:
            print(f"Error checking chatlist invites: {e}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
