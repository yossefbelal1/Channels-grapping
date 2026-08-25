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

    print(f"Testing DialogFilter update peer-by-peer across {len(all_admin_map)} admin peers...")

    accepted_peers = []
    rejected_peers = []

    for cid, d in all_admin_map.items():
        test_filter = DialogFilter(
            id=99,
            title=TextWithEntities(text="Test_Single", entities=[]),
            pinned_peers=[],
            include_peers=[d.input_entity],
            exclude_peers=[],
            contacts=False, non_contacts=False, groups=False, broadcasts=False, bots=False,
            exclude_muted=False, exclude_read=False, exclude_archived=False
        )
        try:
            await client(messages_fn.UpdateDialogFilterRequest(id=99, filter=test_filter))
            
            # Re-read filter 99
            res = await client(messages_fn.GetDialogFiltersRequest())
            saved = None
            for f in res.filters:
                if getattr(f, 'id', None) == 99:
                    saved = f
                    break
                    
            inc = getattr(saved, 'include_peers', []) if saved else []
            if len(inc) == 1:
                accepted_peers.append(d)
            else:
                rejected_peers.append(d)
        except Exception as err:
            rejected_peers.append((d, str(err)))

    # Cleanup test filter 99
    try:
        await client(messages_fn.UpdateDialogFilterRequest(id=99, filter=None))
    except Exception:
        pass

    print(f"\n--- DIALOG FILTER ACCEPTANCE RESULTS ---")
    print(f"✓ ACCEPTED BY TELEGRAM SERVER: {len(accepted_peers)}")
    print(f"❌ REJECTED BY TELEGRAM SERVER: {len(rejected_peers)}")

    print(f"\nSample Accepted Peers ({min(5, len(accepted_peers))}):")
    for d in accepted_peers[:5]:
        ent = d.entity
        print(f"  - '{d.name}' (@{getattr(ent, 'username', 'N/A')}) creator={getattr(ent, 'creator', False)}")

    print(f"\nSample Rejected Peers ({min(10, len(rejected_peers))}):")
    for item in rejected_peers[:10]:
        if isinstance(item, tuple):
            d, err = item
            print(f"  - '{d.name}' (@{getattr(d.entity, 'username', 'N/A')}) creator={getattr(d.entity, 'creator', False)} -> Error: {err}")
        else:
            d = item
            print(f"  - '{d.name}' (@{getattr(d.entity, 'username', 'N/A')}) creator={getattr(d.entity, 'creator', False)} (Server silently stripped peer)")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
