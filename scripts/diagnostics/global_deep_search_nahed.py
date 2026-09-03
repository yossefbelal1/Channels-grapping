import asyncio
import os
import sys
import shutil
import json
from telethon import TelegramClient
from telethon.tl.types import User, Channel
from telethon.tl.functions.contacts import SearchRequest

async def global_deep_search_nahed():
    # Setup temporary session to avoid sqlite db lock
    orig_path = "sessions/validator_session.session"
    temp_path = "sessions/temp_nahed_deep.session"
    if os.path.exists(orig_path):
        shutil.copyfile(orig_path, temp_path)
        
    session_file = "sessions/temp_nahed_deep"
    api_id = 39064636
    api_hash = "72d90d8ac46e9293e3d5254d9645e4f9"
    
    client = TelegramClient(session_file, api_id, api_hash)
    await client.connect()
    
    if not await client.is_user_authorized():
        print("Not authorized.")
        return []
        
    print("Connected to Telegram API! Executing Global Live Search & Permutation Scan for 'ناهد'...")
    
    found_profiles = {}
    
    # 1. TELEGRAM GLOBAL LIVE SEARCH QUERIES
    search_queries = [
        "ناهد إعلانات", "ناهد اعلانات", "ناهد تبادل", "ناهد ads", "ناهد exchange",
        "Nahed Ads", "Nahed exchange", "Nahed marketing", "Nahed Media",
        "ناهد ترويج", "ناهد تسويق", "ناهد فوركس", "ناهد VIP", "ناهد قنوات",
        "Ads Nahed", "Exchange Nahed"
    ]
    
    for q in search_queries:
        try:
            res = await client(SearchRequest(q=q, limit=50))
            # Check users
            for u in res.users:
                if getattr(u, 'bot', False):
                    continue
                uname = getattr(u, 'username', '')
                fname = getattr(u, 'first_name', '') or ''
                lname = getattr(u, 'last_name', '') or ''
                full_name = f"{fname} {lname}".strip()
                
                key = uname.lower() if uname else f"id_{u.id}"
                if key not in found_profiles:
                    found_profiles[key] = {
                        'username': f"@{uname}" if uname else "No Username",
                        'display_name': full_name,
                        'id': u.id,
                        'phone': getattr(u, 'phone', 'Private'),
                        'type': 'Human Person (Telegram Global Search Result)',
                        'matched_query': q
                    }
                    print(f"[+] FOUND VIA GLOBAL SEARCH: @{uname} -> Name: '{full_name}' (ID: {u.id})")
            
            # Check channels/chats
            for c in res.chats:
                title = getattr(c, 'title', '') or ''
                uname = getattr(c, 'username', '')
                key = uname.lower() if uname else f"id_{c.id}"
                if key not in found_profiles:
                    found_profiles[key] = {
                        'username': f"@{uname}" if uname else "No Username",
                        'display_name': title,
                        'id': c.id,
                        'type': 'Channel/Group (Telegram Global Search Result)',
                        'matched_query': q
                    }
                    print(f"[+] FOUND CHANNEL VIA GLOBAL SEARCH: @{uname} -> Title: '{title}' (ID: {c.id})")
                    
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"Error searching query '{q}': {e}")
            
    # 2. EXTENSIVE USERNAME PERMUTATIONS RESOLUTION
    base_names = ['nahed', 'nahid', 'naheed', 'nahd', 'nhed', 'nahedd', 'naheeed', 'nnahed']
    suffixes = [
        'ads', '_ads', 'ads_', '_ads_', 'ad', '_ad', 'exchange', '_exchange',
        'adv', '_adv', 'marketing', '_marketing', 'media', '_media', 'promo',
        '_promo', 'promoter', '_promoter', 'buyer', '_buyer', 'tbad', '_tbad',
        'tabadol', '_tabadol', 'vip', '_vip', 'official', '_official',
        '1', '2', '3', '7', '00', '99', '2024', '2025', '2026', '_1', '_2', '_3',
        'ads1', '_ads1', 'ads2', '_ads2', 'ads3', '_ads3', 'ads_vip', '_adspro'
    ]
    prefixes = ['', 'ads_', 'ads', 'adv_', 'el_', 'al_', 'dr_', 'miss_']
    
    permutations = []
    for b in base_names:
        for p in prefixes:
            for s in suffixes:
                permutations.append(f"{p}{b}{s}")
                
    permutations = list(dict.fromkeys(permutations))
    print(f"\nChecking {len(permutations)} targeted handle permutations...")
    
    for h in permutations:
        try:
            entity = await client.get_entity(h)
            if isinstance(entity, User):
                if getattr(entity, 'bot', False):
                    continue
                uname = getattr(entity, 'username', '') or h
                fname = getattr(entity, 'first_name', '') or ''
                lname = getattr(entity, 'last_name', '') or ''
                full_name = f"{fname} {lname}".strip()
                
                key = uname.lower()
                if key not in found_profiles:
                    found_profiles[key] = {
                        'username': f"@{uname}",
                        'display_name': full_name,
                        'id': entity.id,
                        'phone': getattr(entity, 'phone', 'Private'),
                        'type': 'Human Person (Direct Handle Match)',
                        'matched_query': f"Handle: @{h}"
                    }
                    print(f"[+] FOUND VIA HANDLE PERMUTATION: @{uname} -> Name: '{full_name}' (ID: {entity.id})")
            elif isinstance(entity, Channel):
                uname = getattr(entity, 'username', '') or h
                title = getattr(entity, 'title', '') or ''
                key = uname.lower()
                if key not in found_profiles:
                    found_profiles[key] = {
                        'username': f"@{uname}",
                        'display_name': title,
                        'id': entity.id,
                        'type': 'Channel (Direct Handle Match)',
                        'matched_query': f"Handle: @{h}"
                    }
                    print(f"[+] FOUND CHANNEL VIA HANDLE: @{uname} -> Title: '{title}' (ID: {entity.id})")
            await asyncio.sleep(0.2)
        except Exception:
            pass
            
    await client.disconnect()
    
    # Cleanup
    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except Exception:
            pass
            
    res_list = list(found_profiles.values())
    print(f"\n[★] Total unique results found for Nahed: {len(res_list)}")
    
    with open('/app/nahed_global_search_results.json', 'w', encoding='utf-8') as f:
        json.dump(res_list, f, ensure_ascii=False, indent=2)
        
    return res_list

if __name__ == "__main__":
    asyncio.run(global_deep_search_nahed())
