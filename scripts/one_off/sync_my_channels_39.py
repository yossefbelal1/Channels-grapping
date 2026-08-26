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

    print("Fetching ALL dialogs to collect active admin channels...")
    admin_channels = []
    async for d in client.iter_dialogs():
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
                    admin_channels.append(d)

    print(f"\nStrictly detected {len(admin_channels)} active ADMIN channels/groups.")
    admin_peers = [d.input_entity for d in admin_channels]

    # Update My_Channels Folder (ID 122)
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
        print(f"✓ Updated 'My_Channels' folder (ID {my_filter.id}) on Telegram server with all {len(admin_channels)} admin peers!")
    else:
        print("My_Channels folder not found.")

    # Update Exported Share Link
    try:
        folder_input = InputChatlistDialogFilter(filter_id=122)
        invite_res = await client(chatlists_fn.ExportChatlistInviteRequest(
            chatlist=folder_input,
            title="My_Channels",
            peers=admin_peers
        ))
        link_url = getattr(invite_res.invite, 'url', 'Updated')
        print(f"✓ Updated Chatlist Share Link: {link_url} (Contains {len(admin_peers)} admin peers)")
    except Exception as e:
        print(f"Share link update note: {e}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
