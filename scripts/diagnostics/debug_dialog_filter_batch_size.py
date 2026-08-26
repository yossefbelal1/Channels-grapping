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

    print("Fetching active and archived dialogs...")
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
    total_peers = len(admin_peers)
    print(f"Total admin peers: {total_peers}")

    for test_size in [5, 10, 15, 20]:
        test_batch = admin_peers[:test_size]
        f_test = DialogFilter(
            id=125,
            title=TextWithEntities(text=f"Test_{test_size}", entities=[]),
            pinned_peers=[], include_peers=test_batch, exclude_peers=[],
            contacts=False, non_contacts=False, groups=False, broadcasts=False, bots=False,
            exclude_muted=False, exclude_read=False, exclude_archived=False
        )
        try:
            await client(messages_fn.UpdateDialogFilterRequest(id=125, filter=f_test))
            
            res = await client(messages_fn.GetDialogFiltersRequest())
            saved = None
            for f in res.filters:
                if getattr(f, 'id', None) == 125:
                    saved = f
                    break
            saved_count = len(getattr(saved, 'include_peers', [])) if saved else 0
            print(f"✓ Size {test_size}: Saved {saved_count} / {test_size} peers in folder ID 125!")
        except Exception as e:
            print(f"❌ Size {test_size} Failed: {e}")

    # Delete test filter 125
    try:
        await client(messages_fn.UpdateDialogFilterRequest(id=125, filter=None))
    except Exception:
        pass

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
