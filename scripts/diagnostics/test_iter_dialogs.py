import asyncio
import os
from telethon import TelegramClient
from telethon.tl.functions.messages import GetDialogFiltersRequest
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID", "32950512"))
API_HASH = os.getenv("API_HASH", "23f5be247297fe7645193f6f782dad67")
SESSION = os.path.join("sessions", "user_session")

async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        print("Client not authorized!")
        return

    all_dialogs = []
    async for d in client.iter_dialogs(folder=None):
        all_dialogs.append(d)

    print(f"=== TOTAL DIALOGS FETCHED VIA ITER_DIALOGS: {len(all_dialogs)} ===")

    admin_channels = []
    for d in all_dialogs:
        if not (d.is_channel or d.is_group):
            continue
        entity = d.entity
        left = getattr(entity, 'left', False)
        kicked = getattr(entity, 'kicked', False)
        creator = getattr(entity, 'creator', False)
        admin_rights = getattr(entity, 'admin_rights', None)
        
        is_admin = False
        if not left and not kicked:
            if creator or admin_rights is not None:
                is_admin = True

        if is_admin:
            p_id = getattr(d.input_entity, 'channel_id', None) or getattr(d.input_entity, 'chat_id', None) or getattr(d.input_entity, 'id', None)
            username = getattr(entity, 'username', 'N/A')
            admin_channels.append((p_id, d.name, username, creator, admin_rights is not None))

    print(f"\n=== TOTAL ADMIN CHANNELS/GROUPS FOUND: {len(admin_channels)} ===")
    for idx, (p_id, name, username, creator, admin_rights) in enumerate(admin_channels, 1):
        print(f"[{idx:02d}] ID: {p_id} | @{username} | Creator: {creator} | Admin: {admin_rights} | Title: {name}")

    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
