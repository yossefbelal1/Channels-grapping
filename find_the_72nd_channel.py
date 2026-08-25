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

    print("Fetching all dialogs (active + archived)...")
    dialogs_active = await client.get_dialogs(limit=None)
    dialogs_archived = []
    try:
        dialogs_archived = await client.get_dialogs(limit=None, folder=1)
    except Exception:
        pass

    all_dialogs = dialogs_active + dialogs_archived
    channels = [d for d in all_dialogs if d.is_channel or d.is_group]
    print(f"Total dialogs fetched: {len(all_dialogs)} (Channels/Groups: {len(channels)})")

    admin_channels = []
    chat_admins = []
    
    for d in channels:
        ent = d.entity
        name = d.name
        username = getattr(ent, 'username', 'N/A')
        p_id = getattr(d.input_entity, 'channel_id', None) or getattr(d.input_entity, 'chat_id', None) or getattr(d.input_entity, 'user_id', None) or getattr(d.input_entity, 'id', None)
        left = getattr(ent, 'left', False)
        kicked = getattr(ent, 'kicked', False)
        deactivated = getattr(ent, 'deactivated', False)
        creator = getattr(ent, 'creator', False)
        admin_rights = getattr(ent, 'admin_rights', None)

        if not left and not kicked and not deactivated:
            # Check if creator or admin_rights is not None or if is_group Chat
            if creator or admin_rights is not None:
                admin_channels.append((name, username, p_id, creator, admin_rights))
            elif getattr(ent, 'admin', False) or getattr(d, 'is_group', False):
                # Try getting permissions or participant info
                chat_admins.append((name, username, p_id))

    print(f"\n--- DETECTED CREATOR / ADMIN_RIGHTS CHANNELS ({len(admin_channels)}) ---")
    for idx, (n, u, i, c, r) in enumerate(admin_channels, 1):
        print(f"{idx}. '{n}' (@{u}) [id={i}] | creator={c}")

    print(f"\n--- OTHER GROUPS / CHATS ({len(chat_admins)}) ---")
    for idx, (n, u, i) in enumerate(chat_admins, 1):
        print(f"{idx}. '{n}' (@{u}) [id={i}]")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
