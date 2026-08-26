import os
import sys
import json
import asyncio
import re
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

def extract_contacts_local(text: str, description: str, channel_username: str) -> dict:
    contacts = {
        'website': None,
        'email': None,
        'whatsapp': None,
        'contact_username': None
    }
    
    combined_text = f"{text} {description}"
    
    # 1. Website
    web_match = re.search(
        r'https?://(?:www\.)?(?!(?:t\.me|telegram\.(?:me|dog|org|space)))([a-zA-Z0-9-]+\.[a-zA-Z]{2,6})[^\s]*',
        combined_text,
        re.IGNORECASE
    )
    if web_match:
        contacts['website'] = web_match.group(0).rstrip('.,;)!}"\'')
        
    # 2. Email
    email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', combined_text)
    if email_match:
        contacts['email'] = email_match.group(0)
        
    # 3. WhatsApp
    wa_link_match = re.search(
        r'(?:wa\.me/|api\.whatsapp\.com/send\?phone=|whatsapp:)\+?([0-9]{9,15})',
        combined_text,
        re.IGNORECASE
    )
    if wa_link_match:
        contacts['whatsapp'] = f"+{wa_link_match.group(1)}"
    else:
        phone_match = re.search(
            r'\+?(966|971|965|968|973|962|961|963|967|964|20|90|44|1)[0-9\s-]{7,15}',
            combined_text
        )
        if phone_match:
            num = re.sub(r'[\s-]', '', phone_match.group(0))
            if not num.startswith('+'):
                num = f"+{num}"
            contacts['whatsapp'] = num

    # 4. Telegram support/admin username
    contact_username = None
    keywords_pattern = (
        r'للتواصل|تواصل|للاشتراك|اشتراك|الادارة|الاداره|المشرف|الدعم|دعم|المسؤول|المسئول|'
        r'للاستفسار|استفسار|حسابي|خاص|راسلني|راسلنا|تواصل معي|راسلني على|ارسل لي|للتواصل مع|للتواصل عبر|'
        r'admin|administrator|support|contact|help|owner|manager|ceo|inquiry|subscribe|subscription|pm|dm|chat|personal|me'
    )
    
    # Description check
    match_desc_fwd = re.search(r'(?:' + keywords_pattern + r')\s*[:\-\x20]*\s*@([a-zA-Z0-9_]{5,32})', description or '', re.IGNORECASE)
    if match_desc_fwd:
        contact_username = match_desc_fwd.group(1)
    else:
        match_desc_bwd = re.search(r'@([a-zA-Z0-9_]{5,32})\s*[:\-\x20]*\s*(?:' + keywords_pattern + r')', description or '', re.IGNORECASE)
        if match_desc_bwd:
            contact_username = match_desc_bwd.group(1)
        else:
            all_desc = re.findall(r'@([a-zA-Z0-9_]{5,32})', description or '')
            for u in all_desc:
                if u.lower() != channel_username.lower() and u.lower() not in ('vip', 'premium', 'joinchat', 'channel', 'bot', 'ads', 'link', 'group', 'telegram'):
                    contact_username = u
                    break
                    
    # Messages text check
    if not contact_username:
        match_txt_fwd = re.search(r'(?:' + keywords_pattern + r')\s*[:\-\x20]*\s*@([a-zA-Z0-9_]{5,32})', text or '', re.IGNORECASE)
        if match_txt_fwd:
            contact_username = match_txt_fwd.group(1)
        else:
            match_txt_bwd = re.search(r'@([a-zA-Z0-9_]{5,32})\s*[:\-\x20]*\s*(?:' + keywords_pattern + r')', text or '', re.IGNORECASE)
            if match_txt_bwd:
                contact_username = match_txt_bwd.group(1)
            else:
                all_text_usernames = re.findall(r'@([a-zA-Z0-9_]{5,32})', text or '')
                for u in all_text_usernames:
                    if u.lower() != channel_username.lower() and u.lower() not in ('vip', 'premium', 'joinchat', 'channel', 'bot', 'ads', 'link', 'group', 'telegram'):
                        contact_username = u
                        break
                        
    if contact_username:
        contacts['contact_username'] = contact_username
        
    return contacts

async def main():
    print("==================================================")
    print("      Telegram Channel Extractor & Seeder         ")
    print("==================================================")
    
    # 1. Configuration
    session_name = input("Enter session name [default: user_extract_session]: ").strip()
    if not session_name:
        session_name = "user_extract_session"
        
    print("\nYou can use a default API ID/Hash from existing accounts configuration.")
    api_id_val = 32950512
    api_hash_val = "23f5be247297fe7645193f6f782dad67"
    
    use_default = input(f"Use default API credentials? (y/n) [default: y]: ").strip().lower()
    if use_default == 'n':
        try:
            api_id_val = int(input("Enter API ID: ").strip())
            api_hash_val = input("Enter API Hash: ").strip()
        except ValueError:
            print("Invalid API ID. Exiting.")
            sys.exit(1)
            
    # Resolve path
    session_dir = "sessions"
    os.makedirs(session_dir, exist_ok=True)
    session_path = os.path.join(session_dir, session_name)
    
    # 2. Authenticate and connect
    print(f"\nConnecting to Telegram using session: {session_path}...")
    client = TelegramClient(session_path, api_id_val, api_hash_val)
    await client.connect()
    
    authorized = await client.is_user_authorized()
    if not authorized:
        print("Account is not authorized. Starting interactive login (enter phone, code, 2FA)...")
        try:
            await client.start()
        except Exception as e:
            print(f"Authentication failed: {e}")
            await client.disconnect()
            sys.exit(1)
            
    print("\n[+] Successfully authenticated!")
    print("Fetching all joined chats/channels...")
    
    dialogs = await client.get_dialogs(limit=None)
    channels_to_scan = []
    
    for d in dialogs:
        if d.is_channel or d.is_group:
            channels_to_scan.append(d)
            
    print(f"Found {len(channels_to_scan)} channels/groups joined by this account.")
    
    load_dotenv()
    
    # Connect to DB
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = int(os.getenv("DB_PORT", 5432))
    db_name = os.getenv("DB_NAME", "leadhunter_db")
    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD", "")
    
    print("\nConnecting to database and extracting channel contacts...")
    try:
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            dbname=db_name,
            user=db_user,
            password=db_password
        )
        conn.autocommit = True
        cur = conn.cursor()
    except Exception as e:
        print(f"Database connection failed: {e}")
        await client.disconnect()
        sys.exit(1)

    leads_resolved = 0
    seeds_added = 0
    errors_count = 0

    for idx, d in enumerate(channels_to_scan, 1):
        entity = d.entity
        name = d.name
        is_group = d.is_group
        
        # Determine username/identity key
        has_username = getattr(entity, 'username', None)
        ch_username = entity.username if has_username else f"private_{entity.id}"
        
        print(f"[{idx}/{len(channels_to_scan)}] Processing: '{name}' (@{ch_username})...")
        
        # 1. Fetch description and recent posts
        about = ""
        posts_text = ""
        member_count = getattr(entity, 'participants_count', 0)
        
        try:
            full_chat = await client(GetFullChannelRequest(entity))
            about = full_chat.full_chat.about or ""
            member_count = full_chat.full_chat.participants_count or member_count
        except Exception:
            pass
            
        try:
            messages = await client.get_messages(entity, limit=30)
            posts_text = " \n ".join([m.message for m in messages if m.message])
        except Exception:
            pass
            
        # 2. Extract contacts
        contacts = extract_contacts_local(posts_text, about, ch_username)
        c_user = contacts.get('contact_username')
        c_wa = contacts.get('whatsapp')
        c_web = contacts.get('website')
        
        if c_user or c_wa or c_web:
            # Resolved a contact! Insert/update directly in leads
            try:
                cur.execute("""
                    INSERT INTO leads (
                        channel_username, member_count, contact_username, whatsapp, website, status,
                        forex_category, forex_intent_score, lead_score, tier, is_group, description, last_activity
                    ) VALUES (
                        %s, %s, %s, %s, %s, 'new',
                        'unknown', 80, 80, 'Tier_D', %s, %s, NOW()
                    ) ON CONFLICT (channel_username) DO UPDATE SET
                        member_count = EXCLUDED.member_count,
                        contact_username = COALESCE(NULLIF(leads.contact_username, ''), EXCLUDED.contact_username),
                        whatsapp = COALESCE(NULLIF(leads.whatsapp, ''), EXCLUDED.whatsapp),
                        website = COALESCE(NULLIF(leads.website, ''), EXCLUDED.website),
                        description = COALESCE(NULLIF(leads.description, ''), EXCLUDED.description),
                        last_activity = NOW()
                """, (
                    ch_username, member_count, c_user, c_wa, c_web, is_group, about
                ))
                print(f"  [+] SUCCESS: Resolved contact @{c_user} (WA: {c_wa}, Web: {c_web}) for '{name}'")
                leads_resolved += 1
            except Exception as db_err:
                print(f"  [-] Database error saving lead '{ch_username}': {db_err}")
                errors_count += 1
        else:
            # No owner contact resolved on the spot. If it's a public channel, seed it for background validator queue crawl
            if has_username:
                try:
                    cur.execute("""
                        INSERT INTO seed_channels (channel_username, source, notes, processed)
                        VALUES (%s, 'manual_scan', 'Public channel seeded during extraction', FALSE)
                        ON CONFLICT (channel_username) DO NOTHING
                    """)
                    seeds_added += 1
                except Exception as db_err:
                    print(f"  [-] Database error saving seed '{ch_username}': {db_err}")
                    errors_count += 1
            else:
                print(f"  [!] Skipped private channel '{name}' (no contact details could be resolved)")
                
    cur.close()
    conn.close()
    await client.disconnect()
    
    print("\n" + "="*50)
    print("EXTRACTION & CONTACT RESOLUTION SUMMARY:")
    print(f"  Total Channels Scanned:       {len(channels_to_scan)}")
    print(f"  Leads Resolved & Created:     {leads_resolved}")
    print(f"  Public Seeds Added to Queue:  {seeds_added}")
    print(f"  Errors / Failures:            {errors_count}")
    print("="*50 + "\n")
    print("All resolved channels (both public and private) are now inside your Leads List!")
    print("You can select them on your dashboard and message their owners immediately.")

if __name__ == "__main__":
    asyncio.run(main())
