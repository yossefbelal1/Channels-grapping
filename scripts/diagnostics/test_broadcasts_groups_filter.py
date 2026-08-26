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

    print("Testing DialogFilter with broadcasts=True, groups=True...")

    # Create DialogFilter with broadcasts=True, groups=True
    smart_filter = DialogFilter(
        id=122,
        title=TextWithEntities(text="My_Channels", entities=[]),
        pinned_peers=[],
        include_peers=[],
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
    print("✓ Successfully updated 'My_Channels' Folder (ID 122) with broadcasts=True, groups=True on Telegram Server!")

    # Verify how many dialogs Telegram client returns for folder ID 122
    dialogs_in_folder = await client.get_dialogs(folder=122)
    print(f"\n🎉 TELEGRAM CLIENT DIALOGS IN FOLDER ID 122: {len(dialogs_in_folder)}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
