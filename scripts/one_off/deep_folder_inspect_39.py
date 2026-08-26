import asyncio
import os
import sys
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, User

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

    print("Fetching active and archived dialogs...")
    d_active = await client.get_dialogs(limit=None)
    d_archived = []
    try:
        d_archived = await client.get_dialogs(limit=None, folder=1)
    except Exception as e:
        print(f"Archived error: {e}")

    all_dialogs = d_active + d_archived
    seen_ids = set()

    broadcast_channels = []
    megagroups = []
    basic_groups = []
    other_peers = []

    for d in all_dialogs:
        ent = d.entity
        cid = d.id
        if cid in seen_ids:
            continue

        left = getattr(ent, 'left', False)
        kicked = getattr(ent, 'kicked', False)
        deactivated = getattr(ent, 'deactivated', False)
        creator = getattr(ent, 'creator', False)
        admin_rights = getattr(ent, 'admin_rights', None)
        is_chat_admin = getattr(ent, 'admin', False)

        if not left and not kicked and not deactivated:
            if creator or admin_rights is not None or is_chat_admin:
                seen_ids.add(cid)
                if isinstance(ent, Channel):
                    if getattr(ent, 'broadcast', False):
                        broadcast_channels.append(d)
                    elif getattr(ent, 'megagroup', False):
                        megagroups.append(d)
                    else:
                        broadcast_channels.append(d)
                elif isinstance(ent, Chat):
                    basic_groups.append(d)
                else:
                    other_peers.append(d)

    total_admin_peers = len(broadcast_channels) + len(megagroups) + len(basic_groups) + len(other_peers)

    print(f"\n--- DETAILED BREAKDOWN OF ALL {total_admin_peers} ADMIN ENTITIES ---")
    print(f"1. Broadcast Channels (قنوات أداء/أخبار): {len(broadcast_channels)}")
    print(f"2. Megagroups / Supergroups (جروبات فائقة): {len(megagroups)}")
    print(f"3. Basic Legacy Groups (جروبات عادية قديمة): {len(basic_groups)}")
    print(f"4. Other Peers (صفحات/بوتات): {len(other_peers)}")

    print(f"\n--- LIST OF BROADCAST CHANNELS ({len(broadcast_channels)}) ---")
    for idx, d in enumerate(broadcast_channels, 1):
        print(f"  {idx}. '{d.name}' (@{getattr(d.entity, 'username', 'N/A')})")

    print(f"\n--- LIST OF MEGAGROUPS / SUPERGROUPS ({len(megagroups)}) ---")
    for idx, d in enumerate(megagroups, 1):
        print(f"  {idx}. '{d.name}' (@{getattr(d.entity, 'username', 'N/A')})")

    print(f"\n--- LIST OF BASIC LEGACY GROUPS ({len(basic_groups)}) ---")
    for idx, d in enumerate(basic_groups, 1):
        print(f"  {idx}. '{d.name}' (@{getattr(d.entity, 'username', 'N/A')})")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
