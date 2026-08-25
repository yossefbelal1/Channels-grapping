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

    from telethon.tl.functions.messages import GetDialogFiltersRequest
    from telethon.tl.functions.chatlists import GetExportedInvitesRequest
    from telethon.tl.types import InputChatlistDialogFilter

    print("Fetching dialogs...")
    dialogs_active = await client.get_dialogs(limit=None)
    dialogs_archived = await client.get_dialogs(limit=None, folder=1)
    all_dialogs = dialogs_active + dialogs_archived

    print(f"\n--- Checking 'Gold whale' or similar in all {len(all_dialogs)} dialogs ---")
    for d in all_dialogs:
        if d.is_channel or d.is_group:
            entity = d.entity
            name = d.name
            if "whale" in name.lower() or "gold" in name.lower() or "جروب" in name.lower() or "قناة" in name.lower():
                creator = getattr(entity, 'creator', False)
                admin_rights = getattr(entity, 'admin_rights', None)
                left = getattr(entity, 'left', False)
                kicked = getattr(entity, 'kicked', False)
                print(f"  Name: '{name}' (@{getattr(entity, 'username', 'N/A')}) | creator={creator} | admin_rights={admin_rights} | left={left} | kicked={kicked}")

    print("\n--- Checking Current Folders & My_Channels ---")
    res_filters = await client(GetDialogFiltersRequest())
    filters = res_filters.filters if hasattr(res_filters, 'filters') else []

    my_filter = None
    for f in filters:
        title = f.title.text if hasattr(f.title, 'text') else str(getattr(f, 'title', ''))
        print(f"Folder ID {getattr(f, 'id', None)}: '{title}' ({len(getattr(f, 'include_peers', []))} peers)")
        if title == "My_Channels":
            my_filter = f

    if my_filter:
        print(f"\nPeers inside 'My_Channels' folder:")
        for p in my_filter.include_peers:
            p_id = getattr(p, 'channel_id', None) or getattr(p, 'chat_id', None) or getattr(p, 'id', None)
            match_d = next((d for d in all_dialogs if getattr(d.entity, 'id', None) == p_id), None)
            if match_d:
                ent = match_d.entity
                creator = getattr(ent, 'creator', False)
                admin_rights = getattr(ent, 'admin_rights', None)
                print(f"  - {match_d.name} (@{getattr(ent, 'username', 'N/A')}) | creator={creator} | admin_rights={admin_rights}")
            else:
                print(f"  - [Peer ID {p_id} not in dialogs]")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
