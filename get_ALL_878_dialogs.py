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

    print("Fetching ALL dialogs using iter_dialogs()...")
    all_admin_channels = []
    
    count_dialogs = 0
    async for d in client.iter_dialogs():
        count_dialogs += 1
        if d.is_channel or d.is_group:
            ent = d.entity
            left = getattr(ent, 'left', False)
            kicked = getattr(ent, 'kicked', False)
            deactivated = getattr(ent, 'deactivated', False)
            creator = getattr(ent, 'creator', False)
            admin_rights = getattr(ent, 'admin_rights', None)
            is_chat_admin = getattr(ent, 'admin', False)

            if not left and not kicked and not deactivated:
                if creator or admin_rights is not None or is_chat_admin:
                    all_admin_channels.append(d)

    print(f"\nTotal Dialogs Scanned: {count_dialogs}")
    print(f"Total Strictly Verified Admin Channels/Groups: {len(all_admin_channels)}")

    for idx, d in enumerate(all_admin_channels, 1):
        ent = d.entity
        print(f"  {idx}. '{d.name}' (@{getattr(ent, 'username', 'N/A')}) [id={d.id}]")

    # Sync My_Channels folder ID 122 and share link!
    if len(all_admin_channels) >= 70:
        print(f"\nSyncing My_Channels folder and share link with all {len(all_admin_channels)} admin peers...")
        admin_peers = [d.input_entity for d in all_admin_channels]
        
        # 1. Update folder
        filters_res = await client(messages_fn.GetDialogFiltersRequest())
        my_filter = None
        for f in filters_res.filters:
            title = getattr(f, 'title', '')
            if hasattr(title, 'text'):
                title = title.text
            if title == 'My_Channels' or getattr(f, 'id', None) == 122:
                my_filter = f
                break

        if my_filter:
            my_filter.include_peers = admin_peers
            await client(messages_fn.UpdateDialogFilterRequest(id=my_filter.id, filter=my_filter))
            print(f"✓ Updated My_Channels folder (ID {my_filter.id}) on Telegram server with all {len(all_admin_channels)} peers!")

        # 2. Update Share Link
        import telethon.tl.functions.chatlists as chatlists_fn
        from telethon.tl.types import InputFolderPeer, InputChatlistDialogFilter
        folder_input = InputChatlistDialogFilter(filter_id=122)
        try:
            invite_res = await client(chatlists_fn.ExportChatlistInviteRequest(
                chatlist=folder_input,
                title="My_Channels",
                peers=admin_peers
            ))
            print(f"✓ Created/Updated Share link: {getattr(invite_res.invite, 'url', 'Done')} ({len(admin_peers)} peers)")
        except Exception as share_err:
            print(f"Share link update note: {share_err}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
