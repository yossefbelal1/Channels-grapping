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
    from telethon.tl.types import InputChatlistDialogFilter

    print("Fetching ALL dialog filters (folders)...")
    res_filters = await client(messages_fn.GetDialogFiltersRequest())
    filters = res_filters.filters if hasattr(res_filters, 'filters') else []

    print(f"\nFound {len(filters)} total filters:")
    for f in filters:
        title = "DEFAULT"
        if hasattr(f, 'title') and f.title:
            title = f.title.text if hasattr(f.title, 'text') else str(f.title)
        
        f_id = getattr(f, 'id', 'N/A')
        inc_peers = getattr(f, 'include_peers', [])
        exc_peers = getattr(f, 'exclude_peers', [])
        print(f"\n--- Folder ID {f_id}: '{title}' ---")
        print(f"    Class: {f.__class__.__name__}")
        print(f"    include_peers count: {len(inc_peers)}")
        print(f"    exclude_peers count: {len(exc_peers)}")
        print(f"    groups={getattr(f, 'groups', None)}, broadcasts={getattr(f, 'broadcasts', None)}, contacts={getattr(f, 'contacts', None)}, non_contacts={getattr(f, 'non_contacts', None)}, bots={getattr(f, 'bots', None)}")

        if f_id != 'N/A' and title != "DEFAULT":
            try:
                exp_res = await client(chatlists_fn.GetExportedInvitesRequest(chatlist=InputChatlistDialogFilter(filter_id=f_id)))
                invites = getattr(exp_res, 'invites', [])
                print(f"    Exported Share Links ({len(invites)}):")
                for inv in invites:
                    print(f"      - Title: '{inv.title}' | URL: {inv.url} | Peers: {len(inv.peers)}")
            except Exception as e:
                print(f"    Exported Share Links check note: {e}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
