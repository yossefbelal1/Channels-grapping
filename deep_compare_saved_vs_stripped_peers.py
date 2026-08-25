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

    all_admin_dialogs = []

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
                    all_admin_dialogs.append(d)

    print(f"Testing peer acceptance ONE BY ONE across all {len(all_admin_dialogs)} admin dialogs...\n")

    accepted = []
    rejected = []

    for idx, d in enumerate(all_admin_dialogs, 1):
        f_single = DialogFilter(
            id=129,
            title=TextWithEntities(text="TestSingle", entities=[]),
            pinned_peers=[], include_peers=[d.input_entity], exclude_peers=[],
            contacts=False, non_contacts=False, groups=False, broadcasts=False, bots=False,
            exclude_muted=False, exclude_read=False, exclude_archived=False
        )
        try:
            await client(messages_fn.UpdateDialogFilterRequest(id=129, filter=f_single))
            res = await client(messages_fn.GetDialogFiltersRequest())
            saved = None
            for f in res.filters:
                if getattr(f, 'id', None) == 129:
                    saved = f
                    break
            inc = getattr(saved, 'include_peers', []) if saved else []
            if len(inc) == 1:
                accepted.append(d)
                print(f"✓ [{idx}/71] ACCEPTED: '{d.name}' (@{getattr(d.entity, 'username', 'N/A')}) [id={d.id}] creator={getattr(d.entity, 'creator', False)}")
            else:
                rejected.append(d)
                print(f"❌ [{idx}/71] STRIPPED: '{d.name}' (@{getattr(d.entity, 'username', 'N/A')}) [id={d.id}] creator={getattr(d.entity, 'creator', False)}")
        except Exception as err:
            rejected.append((d, str(err)))
            print(f"❌ [{idx}/71] ERROR: '{d.name}' -> {err}")

    # Cleanup ID 129
    try:
        await client(messages_fn.UpdateDialogFilterRequest(id=129, filter=None))
    except Exception:
        pass

    print(f"\n==========================================")
    print(f"FINAL SUMMARY:")
    print(f"Total Accepted Peers by Telegram Server: {len(accepted)}")
    print(f"Total Stripped Peers by Telegram Server: {len(rejected)}")
    print(f"==========================================")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
