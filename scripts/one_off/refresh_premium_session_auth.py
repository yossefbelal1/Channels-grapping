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

    # 1. Refresh Me & Premium state
    me = await client.get_me()
    is_premium = getattr(me, 'premium', False)
    print(f"👤 User: {me.first_name} (@{me.username})")
    print(f"🌟 Telegram Premium Status in Telethon Session: {is_premium}")

    # 2. Fetch all admin dialogs
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

    admin_peers = [d.input_entity for d in admin_channels]
    print(f"Total Admin Peers: {len(admin_peers)}")

    # 3. Create fresh DialogFilter
    clean_filter = DialogFilter(
        id=122,
        title=TextWithEntities(text="My_Channels", entities=[]),
        pinned_peers=[],
        include_peers=admin_peers,
        exclude_peers=[],
        contacts=False, non_contacts=False, groups=False, broadcasts=False, bots=False,
        exclude_muted=False, exclude_read=False, exclude_archived=False
    )

    await client(messages_fn.UpdateDialogFilterRequest(id=122, filter=clean_filter))
    print("✓ Sent UpdateDialogFilterRequest(id=122) after refreshing Premium Me session.")

    # 4. Verify GetDialogFiltersRequest
    res = await client(messages_fn.GetDialogFiltersRequest())
    my_f = None
    for f in res.filters:
        if getattr(f, 'id', None) == 122:
            my_f = f
            break

    inc = getattr(my_f, 'include_peers', []) if my_f else []
    print(f"\n🎉 TELEGRAM SERVER POST-PREMIUM CONFIRMATION:")
    print(f"   Include Peers Saved: {len(inc)} / {len(admin_peers)}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
