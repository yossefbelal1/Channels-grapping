import asyncio
from telethon import TelegramClient
from telethon.tl.functions.messages import GetDialogFiltersRequest, ExportChatlistInviteRequest, GetExportedChatlistInvitesRequest
from telethon.tl.types import DialogFilter, InputChatlistDialogFilter

async def main():
    client = TelegramClient('/app/sessions/user_session', 36318125, '5f2ea025376141a257979750c3fc9cf7')
    await client.connect()
    if not await client.is_user_authorized():
        print("user_session NOT authorized!")
        return

    print("Fetching dialogs...")
    dialogs_active = await client.get_dialogs(limit=None)
    dialogs_archived = await client.get_dialogs(limit=None, folder=1)
    all_dialogs = dialogs_active + dialogs_archived

    print(f"Total dialogs: {len(all_dialogs)}")

    # Check channels where user is admin
    admin_dialogs = []
    non_admin_dialogs = []

    for d in all_dialogs:
        if d.is_channel or d.is_group:
            entity = d.entity
            is_admin = False
            if not getattr(entity, 'left', False) and not getattr(entity, 'kicked', False) and not getattr(entity, 'deactivated', False):
                if getattr(entity, 'creator', False):
                    is_admin = True
                elif getattr(entity, 'admin_rights', None) is not None:
                    is_admin = True
            
            if is_admin:
                admin_dialogs.append(d)
            else:
                non_admin_dialogs.append(d)

    print(f"\n--- Detected ADMIN dialogs ({len(admin_dialogs)}) ---")
    for d in admin_dialogs[:10]:
        print(f"  [ADMIN] {d.name} (@{getattr(d.entity, 'username', 'N/A')}) - creator={getattr(d.entity, 'creator', False)}, admin_rights={getattr(d.entity, 'admin_rights', None)}")

    # Search for "Gold whale"
    print("\n--- Searching for 'Gold' or 'whale' ---")
    for d in all_dialogs:
        if "whale" in d.name.lower() or "gold" in d.name.lower():
            entity = d.entity
            is_admin = getattr(entity, 'creator', False) or (getattr(entity, 'admin_rights', None) is not None)
            print(f"  Match: {d.name} (@{getattr(entity, 'username', 'N/A')}) | is_admin={is_admin} | creator={getattr(entity, 'creator', False)} | admin_rights={getattr(entity, 'admin_rights', None)} | left={getattr(entity, 'left', False)}")

    # Check Telegram Dialog Filters (Folders)
    print("\n--- Telegram Dialog Filters (Folders) ---")
    res_filters = await client(GetDialogFiltersRequest())
    filters = res_filters.filters if hasattr(res_filters, 'filters') else []

    for f in filters:
        title = f.title.text if hasattr(f.title, 'text') else str(getattr(f, 'title', ''))
        print(f"Folder ID {getattr(f, 'id', None)}: '{title}' - included_peers: {len(getattr(f, 'include_peers', []))}")
        if title == "My_Channels":
            print(f"  Detail of My_Channels peers:")
            for p in getattr(f, 'include_peers', []):
                p_id = getattr(p, 'channel_id', None) or getattr(p, 'chat_id', None) or getattr(p, 'id', None)
                # find matching dialog
                match_d = next((d for d in all_dialogs if getattr(d.entity, 'id', None) == p_id), None)
                if match_d:
                    is_adm = getattr(match_d.entity, 'creator', False) or (getattr(match_d.entity, 'admin_rights', None) is not None)
                    print(f"    - {match_d.name} (@{getattr(match_d.entity, 'username', 'N/A')}) | p_id={p_id} | is_admin={is_adm}")
                else:
                    print(f"    - [Peer p_id={p_id} NOT found in current dialogs]")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
