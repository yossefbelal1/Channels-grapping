"""
Clean approach: Scan ALL dialogs fresh, find ALL admin channels, 
try to save ALL at once to filter, then diagnose which ones get stripped.
No hardcoded IDs - everything comes from the fresh session dialogs.
"""
import asyncio
import os
import sys
from telethon import TelegramClient
from telethon.tl.functions.messages import UpdateDialogFilterRequest, GetDialogFiltersRequest
from telethon.tl.types import (
    DialogFilter, TextWithEntities,
    InputPeerChannel, InputPeerChat, Channel, Chat
)

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from tg_manager import get_session_path

async def main():
    session_path = get_session_path("user_session")
    client = TelegramClient(session_path, 36318125, '5f2ea025376141a257979750c3fc9cf7')
    await client.connect()
    if not await client.is_user_authorized():
        print("NOT authorized!")
        await client.disconnect()
        return

    me = await client.get_me()
    print(f"Logged in as: {me.first_name} (@{me.username}) | Premium: {me.premium}")

    print("\n=== SCANNING ALL DIALOGS FOR ADMIN CHANNELS ===")
    all_admin_peers = []   # (id, title, input_peer)
    total_scanned = 0

    # Scan active dialogs
    async for dialog in client.iter_dialogs(limit=None):
        total_scanned += 1
        ent = dialog.entity
        if not isinstance(ent, (Channel, Chat)):
            continue
        
        # Skip left/kicked/deactivated
        if getattr(ent, 'left', False) or getattr(ent, 'kicked', False) or getattr(ent, 'deactivated', False):
            continue

        is_admin = (
            getattr(ent, 'creator', False) or
            getattr(ent, 'admin_rights', None) is not None or
            getattr(ent, 'admin', False)
        )
        if is_admin:
            try:
                ip = dialog.input_entity
                all_admin_peers.append((ent.id, getattr(ent, 'title', str(ent.id)), ip))
            except Exception as e:
                print(f"  Skipping {getattr(ent, 'title', ent.id)}: {e}")

    # Scan archived dialogs
    async for dialog in client.iter_dialogs(limit=None, folder=1):
        total_scanned += 1
        ent = dialog.entity
        if not isinstance(ent, (Channel, Chat)):
            continue
        if getattr(ent, 'left', False) or getattr(ent, 'kicked', False) or getattr(ent, 'deactivated', False):
            continue
        is_admin = (
            getattr(ent, 'creator', False) or
            getattr(ent, 'admin_rights', None) is not None or
            getattr(ent, 'admin', False)
        )
        if is_admin:
            try:
                ip = dialog.input_entity
                # avoid duplicates
                if not any(p[0] == ent.id for p in all_admin_peers):
                    all_admin_peers.append((ent.id, getattr(ent, 'title', str(ent.id)), ip))
            except Exception as e:
                print(f"  Archived skip {getattr(ent, 'title', ent.id)}: {e}")

    print(f"Total dialogs scanned: {total_scanned}")
    print(f"Total admin peers found: {len(all_admin_peers)}")
    print("\nAll admin channels:")
    for i, (cid, title, _) in enumerate(all_admin_peers, 1):
        print(f"  {i:2d}. {title} (ID={cid})")

    # Try saving ALL at once to filter 122
    print(f"\n=== SAVING ALL {len(all_admin_peers)} TO My_Channels (ID=122) ===")
    input_peers = [p[2] for p in all_admin_peers]
    
    full_filter = DialogFilter(
        id=122,
        title=TextWithEntities(text="My_Channels", entities=[]),
        pinned_peers=[], include_peers=input_peers, exclude_peers=[],
        contacts=False, non_contacts=False, groups=False, broadcasts=False, bots=False,
        exclude_muted=False, exclude_read=False, exclude_archived=False
    )
    try:
        await client(UpdateDialogFilterRequest(id=122, filter=full_filter))
        print("Filter update sent!")
    except Exception as e:
        print(f"Error updating filter: {e}")

    # Check how many were actually saved
    res = await client(GetDialogFiltersRequest())
    saved_count = 0
    for f in res.filters:
        if getattr(f, 'id', None) == 122:
            saved_count = len(getattr(f, 'include_peers', []))
            print(f"Saved peers in filter: {saved_count}")
            break

    if saved_count == len(all_admin_peers):
        print(f"\n🎉 PERFECT! All {saved_count} admin channels saved to My_Channels!")
    else:
        diff = len(all_admin_peers) - saved_count
        print(f"\n⚠ Only {saved_count}/{len(all_admin_peers)} saved. {diff} were rejected by server.")
        
        # Binary search: find which ones get rejected
        print("\n=== BINARY SEARCH: FINDING REJECTED CHANNELS ===")
        rejected = []
        accepted_ids = set()
        
        for cid, title, ip in all_admin_peers:
            test_filter = DialogFilter(
                id=130,
                title=TextWithEntities(text="TestDiag", entities=[]),
                pinned_peers=[], include_peers=[ip], exclude_peers=[],
                contacts=False, non_contacts=False, groups=False, broadcasts=False, bots=False,
                exclude_muted=False, exclude_read=False, exclude_archived=False
            )
            try:
                await client(UpdateDialogFilterRequest(id=130, filter=test_filter))
                res2 = await client(GetDialogFiltersRequest())
                saved_single = 0
                for f in res2.filters:
                    if getattr(f, 'id', None) == 130:
                        saved_single = len(getattr(f, 'include_peers', []))
                        break
                if saved_single == 1:
                    accepted_ids.add(cid)
                    print(f"  ✓ ACCEPTED: {title}")
                else:
                    rejected.append((cid, title))
                    print(f"  ❌ REJECTED: {title} (ID={cid})")
            except Exception as e:
                rejected.append((cid, title))
                print(f"  ❌ ERROR: {title} -> {e}")

        # Cleanup test filter
        try:
            await client(UpdateDialogFilterRequest(id=130, filter=None))
        except Exception:
            pass

        print(f"\n=== FINAL DIAGNOSIS ===")
        print(f"Accepted: {len(accepted_ids)}")
        print(f"Rejected: {len(rejected)}")
        if rejected:
            print("\nRejected channels (CANNOT be added to any folder via API):")
            for cid, title in rejected:
                print(f"  - {title} (ID={cid})")

        # Save only accepted ones
        accepted_peers = [p[2] for p in all_admin_peers if p[0] in accepted_ids]
        if accepted_peers:
            final_filter = DialogFilter(
                id=122,
                title=TextWithEntities(text="My_Channels", entities=[]),
                pinned_peers=[], include_peers=accepted_peers, exclude_peers=[],
                contacts=False, non_contacts=False, groups=False, broadcasts=False, bots=False,
                exclude_muted=False, exclude_read=False, exclude_archived=False
            )
            await client(UpdateDialogFilterRequest(id=122, filter=final_filter))
            res3 = await client(GetDialogFiltersRequest())
            for f in res3.filters:
                if getattr(f, 'id', None) == 122:
                    print(f"\n✅ My_Channels now has {len(getattr(f, 'include_peers', []))} accepted peers saved.")
                    break

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
