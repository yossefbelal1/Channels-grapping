"""
Force-resolve the 32 rejected channels by fetching their message history,
which forces Telegram to return a fresh full access hash in the session.
Then retry adding them all to the My_Channels folder.
"""
import asyncio
import os
import sys
from telethon import TelegramClient
from telethon.tl.functions.messages import UpdateDialogFilterRequest, GetDialogFiltersRequest, GetHistoryRequest
from telethon.tl.functions.channels import GetChannelsRequest, GetFullChannelRequest
from telethon.tl.types import (
    DialogFilter, TextWithEntities, Channel, Chat,
    InputPeerChannel, InputChannel
)

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from tg_manager import get_session_path

# The 32 rejected channel IDs (from fresh scan)
REJECTED_IDS = [
    2132146000, 2703759874, 3935334777, 1526351755, 3745828370,
    4323566851, 3594337653, 3331294074, 3774865254, 1531870553,
    3876055400, 2125984562, 4424333854, 2424695877, 3556765779,
    3971919365, 2047969365, 1983755992, 3954807820, 3964939153,
    3999757764, 2335367368, 1850957457, 1789800455, 4298874694,
    3799397404, 3493935476, 2374105768, 1619031352, 3162275358,
    2030415871, 1222348201
]

async def force_resolve_channel(client, cid, old_input_peer):
    """
    Force-resolve a channel by calling GetChannels and GetHistory,
    which refreshes the access hash stored in the Telethon session.
    Returns a fresh InputPeerChannel or None on failure.
    """
    try:
        # Method 1: GetChannels with current access hash
        result = await client(GetChannelsRequest(id=[old_input_peer]))
        if result.chats:
            fresh_entity = result.chats[0]
            # Force Telethon to cache this entity
            client.session.process_entities(result)
            fresh_ip = await client.get_input_entity(fresh_entity)
            return fresh_ip, "GetChannels"
    except Exception as e:
        pass

    try:
        # Method 2: GetHistory (1 message) - forces full entity resolution
        result = await client(GetHistoryRequest(
            peer=old_input_peer,
            offset_id=0, offset_date=None,
            add_offset=0, limit=1,
            max_id=0, min_id=0, hash=0
        ))
        client.session.process_entities(result)
        fresh_ip = await client.get_input_entity(old_input_peer)
        return fresh_ip, "GetHistory"
    except Exception as e:
        pass

    try:
        # Method 3: GetFullChannel
        result = await client(GetFullChannelRequest(channel=old_input_peer))
        client.session.process_entities(result)
        fresh_ip = await client.get_input_entity(old_input_peer)
        return fresh_ip, "GetFullChannel"
    except Exception as e:
        pass

    return None, "FAILED"


async def test_single_peer(client, input_peer):
    """Test if a single peer can be saved to a temp filter."""
    test_filter = DialogFilter(
        id=130,
        title=TextWithEntities(text="Test", entities=[]),
        pinned_peers=[], include_peers=[input_peer], exclude_peers=[],
        contacts=False, non_contacts=False, groups=False, broadcasts=False, bots=False,
        exclude_muted=False, exclude_read=False, exclude_archived=False
    )
    try:
        await client(UpdateDialogFilterRequest(id=130, filter=test_filter))
        res = await client(GetDialogFiltersRequest())
        for f in res.filters:
            if getattr(f, 'id', None) == 130:
                return len(getattr(f, 'include_peers', [])) == 1
    except Exception:
        pass
    return False


async def main():
    session_path = get_session_path("user_session")
    client = TelegramClient(session_path, 36318125, '5f2ea025376141a257979750c3fc9cf7')
    await client.connect()
    if not await client.is_user_authorized():
        print("NOT authorized!")
        await client.disconnect()
        return

    me = await client.get_me()
    print(f"Logged in as: {me.first_name} | Premium: {me.premium}")

    print("\n=== STEP 1: BUILD FULL DIALOG MAP ===")
    all_admin_peers = []  # (id, title, input_peer) - the 39 accepted ones
    rejected_peers = {}   # id -> (title, input_peer) - the 32 rejected ones

    async for dialog in client.iter_dialogs(limit=None):
        ent = dialog.entity
        if not isinstance(ent, (Channel, Chat)):
            continue
        if getattr(ent, 'left', False) or getattr(ent, 'kicked', False) or getattr(ent, 'deactivated', False):
            continue
        is_admin = (getattr(ent, 'creator', False) or
                    getattr(ent, 'admin_rights', None) is not None or
                    getattr(ent, 'admin', False))
        if is_admin:
            try:
                ip = dialog.input_entity
                if ent.id in REJECTED_IDS:
                    rejected_peers[ent.id] = (getattr(ent, 'title', str(ent.id)), ip)
                else:
                    all_admin_peers.append((ent.id, getattr(ent, 'title', str(ent.id)), ip))
            except Exception:
                pass

    async for dialog in client.iter_dialogs(limit=None, folder=1):
        ent = dialog.entity
        if not isinstance(ent, (Channel, Chat)):
            continue
        if getattr(ent, 'left', False) or getattr(ent, 'kicked', False) or getattr(ent, 'deactivated', False):
            continue
        is_admin = (getattr(ent, 'creator', False) or
                    getattr(ent, 'admin_rights', None) is not None or
                    getattr(ent, 'admin', False))
        if is_admin:
            try:
                ip = dialog.input_entity
                if ent.id in REJECTED_IDS:
                    if ent.id not in rejected_peers:
                        rejected_peers[ent.id] = (getattr(ent, 'title', str(ent.id)), ip)
                else:
                    if not any(p[0] == ent.id for p in all_admin_peers):
                        all_admin_peers.append((ent.id, getattr(ent, 'title', str(ent.id)), ip))
            except Exception:
                pass

    print(f"Accepted peers (39): {len(all_admin_peers)}")
    print(f"Rejected peers found in dialogs: {len(rejected_peers)}")

    print("\n=== STEP 2: FORCE-RESOLVE THE 32 REJECTED CHANNELS ===")
    newly_fixed = []

    for cid in REJECTED_IDS:
        if cid not in rejected_peers:
            print(f"⚠ Not found in dialogs: {cid}")
            continue

        title, old_ip = rejected_peers[cid]
        print(f"\nProcessing: {title} (ID={cid})")

        # Force resolve
        fresh_ip, method = await force_resolve_channel(client, cid, old_ip)
        if fresh_ip is None:
            print(f"  ❌ Could not resolve via any method")
            continue
        print(f"  → Resolved via {method}")

        # Test if it's now accepted
        ok = await test_single_peer(client, fresh_ip)
        if ok:
            newly_fixed.append((cid, title, fresh_ip))
            print(f"  🎉 NOW ACCEPTED!")
        else:
            print(f"  ❌ Still rejected by server")

        await asyncio.sleep(0.5)  # avoid flood

    # Cleanup test filter
    try:
        await client(UpdateDialogFilterRequest(id=130, filter=None))
    except Exception:
        pass

    print(f"\n=== STEP 3: RESULTS ===")
    print(f"Newly fixed: {len(newly_fixed)}")
    print(f"Still rejected: {len(REJECTED_IDS) - len(newly_fixed)}")

    # Build final list: 39 accepted + any newly fixed
    all_final_peers = [p[2] for p in all_admin_peers] + [p[2] for p in newly_fixed]
    print(f"Total for My_Channels: {len(all_final_peers)}")

    print(f"\n=== STEP 4: UPDATE My_Channels FOLDER ===")
    final_filter = DialogFilter(
        id=122,
        title=TextWithEntities(text="My_Channels", entities=[]),
        pinned_peers=[], include_peers=all_final_peers, exclude_peers=[],
        contacts=False, non_contacts=False, groups=False, broadcasts=False, bots=False,
        exclude_muted=False, exclude_read=False, exclude_archived=False
    )
    await client(UpdateDialogFilterRequest(id=122, filter=final_filter))

    res = await client(GetDialogFiltersRequest())
    for f in res.filters:
        if getattr(f, 'id', None) == 122:
            count = len(getattr(f, 'include_peers', []))
            print(f"✅ My_Channels now has {count} channels saved!")
            break

    if newly_fixed:
        print("\nNewly fixed channels:")
        for cid, title, _ in newly_fixed:
            print(f"  + {title}")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
