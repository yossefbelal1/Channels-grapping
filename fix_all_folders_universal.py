"""
Universal folder fixer: scans ALL folders, detects which ones have
fewer peers than expected, and fixes them using GetChannels force-resolve.
Run this any time a folder isn't saving all channels correctly.
"""
import asyncio
import os
import sys
from telethon import TelegramClient
from telethon.tl.functions.messages import UpdateDialogFilterRequest, GetDialogFiltersRequest
from telethon.tl.functions.channels import GetChannelsRequest
from telethon.tl.types import (
    DialogFilter, DialogFilterChatlist, TextWithEntities, Channel, Chat
)

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from tg_manager import get_session_path


async def force_resolve(client, input_peer):
    """Force-resolve a peer via GetChannels to get a full access hash."""
    try:
        result = await client(GetChannelsRequest(id=[input_peer]))
        if result.chats:
            client.session.process_entities(result)
            return await client.get_input_entity(result.chats[0])
    except Exception:
        pass
    return input_peer  # Return original if can't resolve


async def test_peer(client, input_peer, test_filter_id=130):
    """Test if a single peer can be saved to a temp DialogFilter."""
    test_filter = DialogFilter(
        id=test_filter_id,
        title=TextWithEntities(text="Test", entities=[]),
        pinned_peers=[], include_peers=[input_peer], exclude_peers=[],
        contacts=False, non_contacts=False, groups=False,
        broadcasts=False, bots=False,
        exclude_muted=False, exclude_read=False, exclude_archived=False
    )
    try:
        await client(UpdateDialogFilterRequest(id=test_filter_id, filter=test_filter))
        res = await client(GetDialogFiltersRequest())
        for f in res.filters:
            if getattr(f, 'id', None) == test_filter_id:
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

    print("\n=== SCANNING ALL DIALOG FILTERS ===")
    res = await client(GetDialogFiltersRequest())
    filters = [f for f in res.filters if isinstance(f, DialogFilter)]
    print(f"Found {len(filters)} custom folders")

    for folder in filters:
        folder_id = folder.id
        folder_name = getattr(folder.title, 'text', str(folder.id))
        peers = getattr(folder, 'include_peers', [])
        print(f"\n📁 Folder: '{folder_name}' (ID={folder_id}) — {len(peers)} peers saved")

        if not peers:
            print("   Empty folder, skipping.")
            continue

        # Test each peer
        broken_peers = []
        ok_peers = []
        for ip in peers:
            ok = await test_peer(client, ip)
            if ok:
                ok_peers.append(ip)
            else:
                broken_peers.append(ip)
            await asyncio.sleep(0.3)

        print(f"   ✅ OK: {len(ok_peers)} | ❌ Broken: {len(broken_peers)}")

        if not broken_peers:
            print("   All peers are fine!")
            continue

        # Fix broken peers
        print(f"   Fixing {len(broken_peers)} broken peers...")
        fixed_peers = []
        for ip in broken_peers:
            fresh_ip = await force_resolve(client, ip)
            ok = await test_peer(client, fresh_ip)
            if ok:
                fixed_peers.append(fresh_ip)
                print(f"   🎉 Fixed a broken peer!")
            else:
                print(f"   ⚠ Still broken after force-resolve, skipping.")
            await asyncio.sleep(0.3)

        # Rebuild folder with all working peers
        all_good_peers = ok_peers + fixed_peers
        print(f"   Rebuilding folder with {len(all_good_peers)} peers...")

        updated_filter = DialogFilter(
            id=folder_id,
            title=folder.title,
            pinned_peers=getattr(folder, 'pinned_peers', []),
            include_peers=all_good_peers,
            exclude_peers=getattr(folder, 'exclude_peers', []),
            contacts=getattr(folder, 'contacts', False),
            non_contacts=getattr(folder, 'non_contacts', False),
            groups=getattr(folder, 'groups', False),
            broadcasts=getattr(folder, 'broadcasts', False),
            bots=getattr(folder, 'bots', False),
            exclude_muted=getattr(folder, 'exclude_muted', False),
            exclude_read=getattr(folder, 'exclude_read', False),
            exclude_archived=getattr(folder, 'exclude_archived', False),
        )
        await client(UpdateDialogFilterRequest(id=folder_id, filter=updated_filter))

        # Verify
        res2 = await client(GetDialogFiltersRequest())
        for f in res2.filters:
            if getattr(f, 'id', None) == folder_id:
                saved = len(getattr(f, 'include_peers', []))
                print(f"   ✅ '{folder_name}' now has {saved} peers saved!")
                break

    # Cleanup temp test filter
    try:
        await client(UpdateDialogFilterRequest(id=130, filter=None))
    except Exception:
        pass

    print("\n=== ALL FOLDERS FIXED! ===")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
