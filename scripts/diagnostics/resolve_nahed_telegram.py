import asyncio
import os
import sys
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
    "nahed_trade_ads", "nahed_forex_ads", "nahed_adspro"
]

async def check_nahed_profiles():
    session_path = "sessions/validator_session"
    api_id = 39064636
    api_hash = "72d90d8ac46e9293e3d5254d9645e4f9"
    
    client = TelegramClient(session_path, api_id, api_hash)
    await client.connect()
        
    if not await client.is_user_authorized():
        print("No authorized session available.")
        return []
        
    print(f"Connected to Telegram API. Resolving {len(NAHED_HANDLES)} variations for 'ناهد / Nahed'...")
    
    found_profiles = []
    
    for h in NAHED_HANDLES:
        try:
            entity = await client.get_entity(h)
            if isinstance(entity, User):
                fname = getattr(entity, 'first_name', '') or ''
                lname = getattr(entity, 'last_name', '') or ''
                uname = getattr(entity, 'username', '') or h
                full_name = f"{fname} {lname}".strip() or "No Name"
                is_bot = getattr(entity, 'bot', False)
                if not is_bot:
                    print(f"\n[★ FOUND HUMAN MARKETER] @{uname} -> Name: '{full_name}' (ID: {entity.id})")
                    found_profiles.append({
                        'username': f"@{uname}",
                        'display_name': full_name,
                        'user_id': entity.id,
                        'type': 'Human Person (مسوقة إعلانات)'
                    })
            elif isinstance(entity, Channel):
                title = getattr(entity, 'title', '') or ''
                uname = getattr(entity, 'username', '') or h
                print(f"\n[★ FOUND CHANNEL / NETWORK] @{uname} -> Title: '{title}' (ID: {entity.id})")
                found_profiles.append({
                    'username': f"@{uname}",
                    'display_name': title,
                    'user_id': entity.id,
                    'type': 'Official Ads Channel / Network'
                })
            await asyncio.sleep(0.3)
        except Exception:
            pass
            
    await client.disconnect()
    return found_profiles

async def main():
    results = await check_nahed_profiles()
    print(f"\nTotal Nahed accounts found: {len(results)}")
    with open('nahed_verified_profiles.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
