import asyncio
import os
import sys
import json
import re
from telethon import TelegramClient
from telethon.tl.types import User, Channel

# Names to construct handles for
MARKETER_NAMES = [
    'maha', 'hager', 'hagar', 'maysa', 'maisa', 'dina', 'farida', 'faten',
    'azza', 'sara', 'sarah', 'aya', 'nour', 'noor', 'menna', 'yasmine',
    'yasmin', 'reem', 'rania', 'esraa', 'israa', 'hadeer', 'shahd',
    'salma', 'habiba', 'mariam', 'maryam', 'rawan', 'laila', 'layla',
    'nada', 'malak', 'jana', 'fatma', 'khadija', 'shorouk', 'mokhtar',
    'ahmed', 'mohamed', 'ali', 'karim', 'omar', 'youssef', 'zeyad',
    'mahmoud', 'hassan', 'khaled', 'tarek', 'mostafa', 'ibrahim', 'amr',
    'wael', 'sameh', 'tamer', 'hossam', 'marwan', 'ziad', 'samar', 'dalia'
]

# Generate candidate human handles
candidate_handles = []
for n in MARKETER_NAMES:
    candidate_handles.extend([
        f"{n}_ads", f"{n}ads", f"ads_{n}", f"ads{n}",
        f"{n}_exchange", f"{n}exchange",
        f"{n}_adv", f"{n}adv",
        f"{n}_promo", f"{n}promo",
        f"{n}_marketing", f"{n}marketing",
        f"{n}_media", f"{n}media"
    ])

# Add known market handles
candidate_handles.extend([
    "farida_ads", "Adsazza", "fatenexchange", "adprofx", "Growthengine_co",
    "elitetradersad", "protradersad", "maryamads1", "mohamed_ads97", "ads_maneg14",
    "adpromox", "zaintoadvrestm", "maha_ads", "mahaads", "hager_ads", "hagerads",
    "hagar_ads", "hagarads", "maysa_ads", "maysaads", "dina_ads", "dinaads",
    "sara_ads", "saraads", "aya_ads", "ayaads", "nour_ads", "nourads"
])

# Deduplicate
candidate_handles = list(dict.fromkeys(candidate_handles))
print(f"Total candidate marketer handles generated: {len(candidate_handles)}")

async def verify_human_marketers():
    # Use radar_session or validator_session
    client = TelegramClient('sessions/radar_session', 31925523, '6448299ee7fb91c63cbc82511b435594')
    await client.connect()
    
    if not await client.is_user_authorized():
        print("Client not authorized locally, trying validator_session...")
        await client.disconnect()
        client = TelegramClient('sessions/validator_session', 39064636, '72d90d8ac46e9293e3d5254d9645e4f9')
        await client.connect()
        
    if not await client.is_user_authorized():
        print("Session not authorized. Processing offline data.")
        return []

    print("Connected to Telegram API. Resolving live human marketer profiles...")
    
    verified_marketers = []
    
    for i, handle in enumerate(candidate_handles):
        try:
            entity = await client.get_entity(handle)
            # STRICT FILTER: MUST BE HUMAN USER (NOT A BOT, NOT A CHANNEL IF USER ONLY)
            if isinstance(entity, User):
                if getattr(entity, 'bot', False):
                    continue  # SKIP BOTS STRICTLY
                    
                fname = getattr(entity, 'first_name', '') or ''
                lname = getattr(entity, 'last_name', '') or ''
                full_name = f"{fname} {lname}".strip() or "No Name"
                uname = getattr(entity, 'username', '') or handle
                
                print(f"[+] FOUND HUMAN MARKETER: @{uname} -> Name: '{full_name}' (ID: {entity.id})")
                verified_marketers.append({
                    'username': f"@{uname}",
                    'name': full_name,
                    'user_id': entity.id,
                    'type': 'Human Person (مسوق/مسوقة حقيقي)'
                })
            elif isinstance(entity, Channel):
                title = getattr(entity, 'title', '') or ''
                uname = getattr(entity, 'username', '') or handle
                # If channel is an official ads channel for a marketer
                verified_marketers.append({
                    'username': f"@{uname}",
                    'name': title,
                    'user_id': entity.id,
                    'type': 'Official Ads Channel / Agency'
                })
                
            await asyncio.sleep(0.5)  # gentle pacing
        except Exception:
            # Handle doesn't exist or private
            pass
            
    await client.disconnect()
    return verified_marketers

async def main():
    results = await verify_human_marketers()
    print(f"\n[+] Total Live Verified Profiles Found: {len(results)}")
    
    with open('verified_human_marketers.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
