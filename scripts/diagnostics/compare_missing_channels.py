"""
Compare current admin channels with the previously known 71 channels
to find exactly which ones are missing now.
"""
import asyncio
import sys
import os
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from tg_manager import get_session_path

# Previously confirmed 71 admin channels from August 13 scan
# IDs from fresh_scan_and_build_folder.py results
PREVIOUSLY_KNOWN_IDS = {
    # Accepted 39 (from force_refresh results)
    2365215970, 2204432738, 1374392512, 1500428509, 1050833440,
    1582069399, 1615541990, 1785891507, 1892003358, 1964505256,
    2007773117, 2010095302, 2019889820, 2031066392, 2044890987,
    2050553534, 2063793048, 2069723408, 2072327539, 2081419895,
    2093617696, 2106050997, 2107753516, 2109498072, 2112047688,
    2116397658, 2135043682, 2144503199, 2147905003, 2158895271,
    2165832513, 2173028437, 2182893028, 2185988479, 2186524453,
    2193694476, 2198703047, 2201344851, 2229440827,
    # Previously rejected 32 (now fixed)
    2132146000, 2703759874, 3935334777, 1526351755, 3745828370,
    4323566851, 3594337653, 3331294074, 3774865254, 1531870553,
    3876055400, 2125984562, 4424333854, 2424695877, 3556765779,
    3971919365, 2047969365, 1983755992, 3954807820, 3964939153,
    3999757764, 2335367368, 1850957457, 1789800455, 4298874694,
    3799397404, 3493935476, 2374105768, 1619031352, 3162275358,
    2030415871, 1222348201
}

async def main():
    session_path = get_session_path("user_session")
    client = TelegramClient(session_path, 36318125, '5f2ea025376141a257979750c3fc9cf7')
    await client.connect()
    if not await client.is_user_authorized():
        print("NOT authorized!")
        await client.disconnect()
        return

    me = await client.get_me()
    print(f"Logged in as: {me.first_name} (ID={me.id})")

    print("\n=== SCANNING ALL CURRENT ADMIN CHANNELS ===")
    current_admin = {}  # id -> title

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
            current_admin[ent.id] = getattr(ent, 'title', str(ent.id))

    async for dialog in client.iter_dialogs(limit=None, folder=1):
        ent = dialog.entity
        if not isinstance(ent, (Channel, Chat)):
            continue
        if getattr(ent, 'left', False) or getattr(ent, 'kicked', False) or getattr(ent, 'deactivated', False):
            continue
        is_admin = (getattr(ent, 'creator', False) or
                    getattr(ent, 'admin_rights', None) is not None or
                    getattr(ent, 'admin', False))
        if is_admin and ent.id not in current_admin:
            current_admin[ent.id] = getattr(ent, 'title', str(ent.id))

    print(f"Total current admin channels: {len(current_admin)}")

    print("\n=== ALL CURRENT ADMIN CHANNELS ===")
    for i, (cid, title) in enumerate(sorted(current_admin.items(), key=lambda x: x[1]), 1):
        print(f"  {i:2d}. {title} (ID={cid})")

    # Find missing from previously known
    missing_ids = PREVIOUSLY_KNOWN_IDS - set(current_admin.keys())
    new_ids = set(current_admin.keys()) - PREVIOUSLY_KNOWN_IDS

    print(f"\n=== MISSING CHANNELS (were admin before, not now) ===")
    print(f"Missing count: {len(missing_ids)}")
    for cid in sorted(missing_ids):
        # Try to get entity info for missing channel
        title = "Unknown"
        try:
            ent = await client.get_entity(cid)
            title = getattr(ent, 'title', str(cid))
            deactivated = getattr(ent, 'deactivated', False)
            kicked = getattr(ent, 'kicked', False)
            left = getattr(ent, 'left', False)
            status = []
            if deactivated: status.append("DELETED")
            if kicked: status.append("KICKED")
            if left: status.append("LEFT")
            if not status: status.append("still exists - lost admin")
            print(f"  ❌ {title} (ID={cid}) → {', '.join(status)}")
        except Exception as e:
            print(f"  ❌ ID={cid} → Cannot access: {e}")

    if new_ids:
        print(f"\n=== NEW CHANNELS ADDED (not in previous list) ===")
        for cid in sorted(new_ids):
            title = current_admin.get(cid, str(cid))
            print(f"  ✅ {title} (ID={cid})")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
