"""
Fix the حملات folder to contain exactly 5 specific channels:
- MAFIA GOLD (4298874694)
- Pip Masters (3999757764)
- GOLDEX FOREX SIGNALS (2365215970)
- Sherlock Holmes FX (2132146000)
- GOLD PLATINUM TRADER (3935334777)
"""
import asyncio
import sys
import os
from telethon import TelegramClient
from telethon.tl.functions.messages import UpdateDialogFilterRequest, GetDialogFiltersRequest
from telethon.tl.functions.channels import GetChannelsRequest
from telethon.tl.types import DialogFilter, TextWithEntities, Channel, Chat

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from tg_manager import get_session_path

TARGET_CHANNEL_IDS = [
    4298874694,   # MAFIA GOLD
    3999757764,   # Pip Masters
    2365215970,   # GOLDEX FOREX SIGNALS
    2132146000,   # Sherlock Holmes FX
    3935334777,   # GOLD PLATINUM TRADER
]

HAMLAT_FOLDER_ID = 6

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

    # Build dialog map
    print("\nScanning dialogs to find target channels...")
    dialog_map = {}
    async for dialog in client.iter_dialogs(limit=None):
        ent = dialog.entity
        if isinstance(ent, (Channel, Chat)) and ent.id in TARGET_CHANNEL_IDS:
            dialog_map[ent.id] = (getattr(ent, 'title', str(ent.id)), dialog.input_entity)
    async for dialog in client.iter_dialogs(limit=None, folder=1):
        ent = dialog.entity
        if isinstance(ent, (Channel, Chat)) and ent.id in TARGET_CHANNEL_IDS:
            if ent.id not in dialog_map:
                dialog_map[ent.id] = (getattr(ent, 'title', str(ent.id)), dialog.input_entity)

    print(f"Found {len(dialog_map)}/{len(TARGET_CHANNEL_IDS)} target channels in dialogs")

    # Force-resolve each via GetChannels
    print("\nForce-resolving all 5 channels via GetChannels...")
    final_peers = []
    for cid in TARGET_CHANNEL_IDS:
        if cid not in dialog_map:
            print(f"  ❌ NOT FOUND in dialogs: {cid}")
            continue
        title, old_ip = dialog_map[cid]
        try:
            result = await client(GetChannelsRequest(id=[old_ip]))
            if result.chats:
                client.session.process_entities(result)
                fresh_ip = await client.get_input_entity(result.chats[0])
                final_peers.append(fresh_ip)
                print(f"  ✅ Resolved: {title}")
            else:
                final_peers.append(old_ip)
                print(f"  ⚠ Used original: {title}")
        except Exception as e:
            final_peers.append(old_ip)
            print(f"  ⚠ GetChannels failed ({e}), using original: {title}")

    print(f"\nTotal peers to save: {len(final_peers)}")

    # Update حملات folder
    print(f"\nUpdating حملات folder (ID={HAMLAT_FOLDER_ID})...")
    hamlat_filter = DialogFilter(
        id=HAMLAT_FOLDER_ID,
        title=TextWithEntities(text="حملات", entities=[]),
        pinned_peers=[],
        include_peers=final_peers,
        exclude_peers=[],
        contacts=False, non_contacts=False, groups=False,
        broadcasts=False, bots=False,
        exclude_muted=False, exclude_read=False, exclude_archived=False
    )
    await client(UpdateDialogFilterRequest(id=HAMLAT_FOLDER_ID, filter=hamlat_filter))

    # Verify
    res = await client(GetDialogFiltersRequest())
    for f in res.filters:
        if getattr(f, 'id', None) == HAMLAT_FOLDER_ID:
            saved = len(getattr(f, 'include_peers', []))
            print(f"✅ حملات folder now has {saved}/5 channels saved!")
            break

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
