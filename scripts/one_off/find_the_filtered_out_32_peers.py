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

    import telethon.tl.functions.chatlists as chatlists_fn

    print("Fetching active and archived dialogs...")
    d_active = await client.get_dialogs(limit=None)
    d_archived = []
    try:
        d_archived = await client.get_dialogs(limit=None, folder=1)
    except Exception as e:
        print(f"Archived error: {e}")

    all_dialogs = d_active + d_archived
    seen_ids = set()

    all_admin_map = {}

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
                    seen_ids.add(cid)
                    all_admin_map[cid] = d

    print(f"Total Verified Admin Dialogs: {len(all_admin_map)}")

    # Check the Chatlist Link
    slug = "3Eepr2-DWEhkODA0"
    check_res = await client(chatlists_fn.CheckChatlistInviteRequest(slug=slug))
    link_chats = getattr(check_res, 'chats', [])
    link_chat_ids = {c.id for c in link_chats}

    print(f"Chats inside Telegram Share Link: {len(link_chats)}")

    included_in_link = []
    excluded_from_link = []

    for cid, d in all_admin_map.items():
        # Telethon peer id vs raw channel id
        raw_cid = getattr(d.entity, 'id', None)
        if cid in link_chat_ids or raw_cid in link_chat_ids or -cid in link_chat_ids or int(f"-100{raw_cid}") in link_chat_ids:
            included_in_link.append(d)
        else:
            excluded_from_link.append(d)

    print(f"\n--- INCLUDED IN SHARE LINK ({len(included_in_link)}) ---")
    for idx, d in enumerate(included_in_link, 1):
        print(f"  {idx}. '{d.name}' (@{getattr(d.entity, 'username', 'N/A')})")

    print(f"\n--- EXCLUDED FROM SHARE LINK ({len(excluded_from_link)}) ---")
    for idx, d in enumerate(excluded_from_link, 1):
        ent = d.entity
        creator = getattr(ent, 'creator', False)
        admin_rights = getattr(ent, 'admin_rights', None)
        invite_perm = getattr(admin_rights, 'invite_users', False) if admin_rights else False
        print(f"  {idx}. '{d.name}' (@{getattr(ent, 'username', 'N/A')}) [creator={creator}, invite_perm={invite_perm}]")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
