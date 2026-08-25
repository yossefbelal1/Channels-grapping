import asyncio
import os
import sys
from telethon import TelegramClient
from telethon.tl.functions.messages import UpdateDialogFilterRequest, GetDialogFiltersRequest
from telethon.tl.functions.channels import GetChannelsRequest
from telethon.tl.types import DialogFilter, TextWithEntities, InputChannel

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from tg_manager import get_session_path

# These are the 32 channels that were rejected - force-refresh them by raw ID
REJECTED_CHANNEL_IDS = [
    1806690343,  # SCORPION EL GOLD
    2028048756,  # Pip Masters
    1531870553,  # MORX
    1861893882,  # SNIPER GOLD
    2234524888,  # رناي
    1985783592,  # الفوركس في المملكة
    1829561882,  # UK TRADERS
    2275116676,  # ACCOUNT MANAGER
    1916440396,  # الأسطورة للتداول
    2021397897,  # forex signal
    2096578059,  # Professor Al-Dahap
    2079753046,  # AT. TRADING
    2012014276,  # BLACK HORSE ACADEMY
    1960774888,  # Prime Trading
    1883793193,  # Technical_analysis
    2216127695,  # Trade X
    2115268534,  # ماستر تداول الفوركس
    2200399019,  # FOREX PALESTINE
    1926832082,  # THE ROYAL VAULT
    1911003793,  # محمد المطيري
    2244256756,  # MAFIA GOLD
    1903022389,  # AlMANSORI
    2085561483,  # Sherlock Holmes FX
    1851979459,  # جلاد الذهب
    1987773905,  # 3abkreno ElForex
    1881003143,  # Smart Liquidity
    2233918534,  # GOLD PLATINUM TRADER
    2163754834,  # Dr ALi FOREX
    2244388028,  # Dr ALi CRYPTO
    2067162041,  # KING FX
    2047703705,  # سيادة الذهب
    1944009010,  # ARAB ICT
]

async def main():
    session_path = get_session_path("user_session")
    client = TelegramClient(session_path, 36318125, '5f2ea025376141a257979750c3fc9cf7')
    await client.connect()
    if not await client.is_user_authorized():
        print("user_session NOT authorized!")
        await client.disconnect()
        return

    print("=== STEP 1: FORCE-REFRESH ALL 32 REJECTED CHANNELS ===")
    refreshed_peers = []
    failed = []

    # Get active dialogs to build access hash map
    print("Loading fresh dialog list to get access hashes...")
    d_active = await client.get_dialogs(limit=None)
    d_archived = []
    try:
        d_archived = await client.get_dialogs(limit=None, folder=1)
    except Exception:
        pass

    all_dialogs = d_active + d_archived

    # Build id -> dialog map for quick lookup
    dialog_map = {}
    for d in all_dialogs:
        if d.is_channel or d.is_group:
            dialog_map[d.id] = d

    print(f"Loaded {len(dialog_map)} dialogs into map.")

    # Try refreshing each rejected channel
    for cid in REJECTED_CHANNEL_IDS:
        try:
            # Try direct entity lookup first
            ent = await client.get_entity(cid)
            input_peer = await client.get_input_entity(ent)
            refreshed_peers.append((cid, ent, input_peer))
            print(f"✓ Refreshed: {getattr(ent, 'title', str(cid))} (ID={cid})")
        except Exception as e:
            # Try from dialog map
            if cid in dialog_map:
                d = dialog_map[cid]
                try:
                    input_peer = d.input_entity
                    refreshed_peers.append((cid, d.entity, input_peer))
                    print(f"✓ From dialog: {d.name} (ID={cid})")
                except Exception as e2:
                    failed.append((cid, str(e2)))
                    print(f"❌ FAILED: {cid} -> {e2}")
            else:
                failed.append((cid, str(e)))
                print(f"❌ FAILED: {cid} -> {e}")

    print(f"\nRefreshed: {len(refreshed_peers)} | Failed: {len(failed)}")

    if not refreshed_peers:
        print("Nothing to work with. Exiting.")
        await client.disconnect()
        return

    # Get the 39 accepted channels
    print("\n=== STEP 2: GET ACCEPTED 39 CHANNELS ===")
    accepted_peers = []
    seen_ids = set([r[0] for r in refreshed_peers])

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
                    accepted_peers.append(d.input_entity)
                    seen_ids.add(cid)

    print(f"Accepted peers: {len(accepted_peers)}")

    # All input peers = accepted + freshly refreshed rejected
    all_input_peers = accepted_peers + [r[2] for r in refreshed_peers]
    print(f"Total input peers to save: {len(all_input_peers)}")

    print("\n=== STEP 3: TEST ADDING REFRESHED REJECTED CHANNELS ONE-BY-ONE ===")
    newly_accepted = []
    still_rejected = []

    for cid, ent, input_peer in refreshed_peers:
        test_filter = DialogFilter(
            id=130,
            title=TextWithEntities(text="TestRefresh", entities=[]),
            pinned_peers=[], include_peers=[input_peer], exclude_peers=[],
            contacts=False, non_contacts=False, groups=False, broadcasts=False, bots=False,
            exclude_muted=False, exclude_read=False, exclude_archived=False
        )
        try:
            await client(UpdateDialogFilterRequest(id=130, filter=test_filter))
            res = await client(GetDialogFiltersRequest())
            saved = None
            for f in res.filters:
                if getattr(f, 'id', None) == 130:
                    saved = f
                    break
            inc = getattr(saved, 'include_peers', []) if saved else []
            if len(inc) == 1:
                newly_accepted.append((cid, getattr(ent, 'title', str(cid)), input_peer))
                print(f"🎉 NOW ACCEPTED: {getattr(ent, 'title', str(cid))} (ID={cid})")
            else:
                still_rejected.append((cid, getattr(ent, 'title', str(cid))))
                print(f"❌ Still rejected: {getattr(ent, 'title', str(cid))} (ID={cid})")
        except Exception as err:
            still_rejected.append((cid, str(err)))
            print(f"❌ Error: {getattr(ent, 'title', str(cid))} -> {err}")

    # Cleanup test filter 130
    try:
        await client(UpdateDialogFilterRequest(id=130, filter=None))
    except Exception:
        pass

    print(f"\n=== RESULTS ===")
    print(f"Newly Accepted After Refresh: {len(newly_accepted)}")
    print(f"Still Rejected: {len(still_rejected)}")

    # Build final combined filter with all valid peers
    final_peers = accepted_peers + [r[2] for r in newly_accepted]
    print(f"\n=== STEP 4: UPDATE My_Channels WITH ALL {len(final_peers)} VALID PEERS ===")

    final_filter = DialogFilter(
        id=122,
        title=TextWithEntities(text="My_Channels", entities=[]),
        pinned_peers=[], include_peers=final_peers, exclude_peers=[],
        contacts=False, non_contacts=False, groups=False, broadcasts=False, bots=False,
        exclude_muted=False, exclude_read=False, exclude_archived=False
    )

    await client(UpdateDialogFilterRequest(id=122, filter=final_filter))
    res_check = await client(GetDialogFiltersRequest())
    for f in res_check.filters:
        if getattr(f, 'id', None) == 122:
            print(f"🎉 FINAL My_Channels folder has {len(getattr(f, 'include_peers', []))} peers saved!")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
