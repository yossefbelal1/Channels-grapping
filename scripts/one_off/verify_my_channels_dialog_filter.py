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
    from telethon.tl.types import DialogFilter, TextWithEntities

    print("Fetching all active and archived dialogs...")
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
    print(f"Verified {len(admin_peers_all)} admin channels/groups.")

    # Create DialogFilter with broadcasts=True, groups=True AND explicit include_peers
    smart_filter = DialogFilter(
        id=122,
        title=TextWithEntities(text="My_Channels", entities=[]),
        pinned_peers=[],
        include_peers=admin_peers_all,
        exclude_peers=[],
        contacts=False,
        non_contacts=False,
        groups=True,
        broadcasts=True,
        bots=False,
        exclude_muted=False,
        exclude_read=False,
        exclude_archived=False
    )

    await client(messages_fn.UpdateDialogFilterRequest(id=122, filter=smart_filter))
    print("✓ Updated My_Channels Folder (ID 122) with broadcasts=True, groups=True and explicit peers.")

    # Verify GetDialogFiltersRequest
    filters_res = await client(messages_fn.GetDialogFiltersRequest())
    my_filter = None
    for f in filters_res.filters:
        fid = getattr(f, 'id', None)
        title = getattr(f, 'title', '')
        if hasattr(title, 'text'):
            title = title.text
        if fid == 122 or title == 'My_Channels':
            my_filter = f
            break

    if my_filter:
        print(f"\n🎉 TELEGRAM SERVER FILTER CONFIRMATION:")
        print(f"   Folder Title: '{getattr(my_filter.title, 'text', my_filter.title)}'")
        print(f"   Broadcasts Flag: {getattr(my_filter, 'broadcasts', False)}")
        print(f"   Groups Flag: {getattr(my_filter, 'groups', False)}")
        print(f"   Explicit Include Peers: {len(getattr(my_filter, 'include_peers', []))}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
