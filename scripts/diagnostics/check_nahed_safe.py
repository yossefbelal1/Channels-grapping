import asyncio
import os
import sys
import shutil
import json
from telethon import TelegramClient
from telethon.tl.types import User, Channel

NAHED_HANDLES = [
    "nahed_ads", "nahedads", "ads_nahed", "adsnahed",
    "nahed_ads1", "nahedads1", "nahed_ads2", "nahedads2",
    "nahed_ads3", "nahedads3", "nahed_ads4", "nahedads4",
    "nahed_exchange", "nahedexchange", "ads_nahed1",
    "nahed_marketing", "nahedmarketing",
    "nahed_adv", "nahedadv", "nahed_media",
    "nahed_promo", "nahedpromo", "nahed_promoter",
    "nahedads_official", "nahed_ads_official",
    "nahed_ad", "nahedad", "adsnahed1",
    "nahed_ads_vip", "nahed_vip_ads", "nahed_exchange1",
    "nahed_trade_ads", "nahed_forex_ads", "nahed_adspro",
    "nahed_marketing1", "nahed_promo1", "nahed_exchange_vip",
    "nahid_ads", "nahidads", "ads_nahid", "adsnahid",
    "nahid_exchange", "nahidexchange", "nahid_adv", "nahidadv",
    "nahid_marketing", "nahidmarketing", "nahid_promo",
    "naheed_ads", "naheedads", "ads_naheed", "adsnaheed",
    "nahed1_ads", "nahed2_ads", "nahed3_ads", "nahed_official_ads"
]

async def check():
    # Copy to temp session to avoid sqlite lock
    orig_path = "sessions/validator_session.session"
    temp_path = "sessions/temp_nahed_check.session"
    if os.path.exists(orig_path):
        shutil.copyfile(orig_path, temp_path)
        
    session_file = "sessions/temp_nahed_check"
    api_id = 39064636
    api_hash = "72d90d8ac46e9293e3d5254d9645e4f9"
    
    client = TelegramClient(session_file, api_id, api_hash)
    await client.connect()
    
    if not await client.is_user_authorized():
        print("Not authorized.")
        return
        
    print(f"Connected! Checking {len(NAHED_HANDLES)} variations for Nahed...")
    
    found = []
    for h in NAHED_HANDLES:
        try:
            entity = await client.get_entity(h)
            if isinstance(entity, User):
                fname = getattr(entity, 'first_name', '') or ''
                lname = getattr(entity, 'last_name', '') or ''
                full_name = f"{fname} {lname}".strip()
                uname = getattr(entity, 'username', '') or h
                is_bot = getattr(entity, 'bot', False)
                if not is_bot:
                    print(f"[+] FOUND HUMAN USER: @{uname} -> Name: '{full_name}' (ID: {entity.id})")
                    found.append({
                        'username': f"@{uname}",
                        'display_name': full_name,
                        'id': entity.id,
                        'type': 'Human Person (مسوقة إعلانات)'
                    })
            elif isinstance(entity, Channel):
                title = getattr(entity, 'title', '') or ''
                uname = getattr(entity, 'username', '') or h
                print(f"[+] FOUND CHANNEL / NETWORK: @{uname} -> Title: '{title}' (ID: {entity.id})")
                found.append({
                    'username': f"@{uname}",
                    'display_name': title,
                    'id': entity.id,
                    'type': 'Official Ads Channel'
                })
            await asyncio.sleep(0.3)
        except Exception:
            pass
            
    await client.disconnect()
    
    # Cleanup temp
    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except Exception:
            pass
            
    print(f"\nTotal Verified Nahed profiles found: {len(found)}")
    with open('/app/nahed_found.json', 'w', encoding='utf-8') as f:
        json.dump(found, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    asyncio.run(check())
