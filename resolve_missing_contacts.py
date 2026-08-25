import os
import sys
import json
import asyncio
import logging
import re
from dotenv import load_dotenv
import redis
import psycopg2
from psycopg2.extras import RealDictCursor
from telethon import TelegramClient, functions, errors
from telethon.tl.functions.channels import GetFullChannelRequest
from tg_manager import TelegramManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

load_dotenv()

# PostgreSQL credentials
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "leadhunter_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        cursor_factory=RealDictCursor
    )

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
    logging.info("Starting Contact Resolution Script...")
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    redis_conn = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
    
    # Initialize Telegram Manager
    tg_manager = TelegramManager(redis_conn, session_name="user_session", worker_type="contact_resolver")
    await tg_manager.start_all()
    
    client = tg_manager.clients.get("user_session")
    if not client or not client.is_connected():
        logging.error("Failed to connect user_session client.")
        await tg_manager.disconnect_all()
        return

    # Find leads lacking contact_username
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, channel_username 
        FROM leads 
        WHERE (contact_username IS NULL OR contact_username = '') 
          AND status != 'rejected'
        ORDER BY member_count DESC
    """)
    leads = cur.fetchall()
    logging.info(f"Found {len(leads)} leads lacking contact usernames. Resolving...")

    updated_count = 0

    for lead in leads:
        lead_id = lead['id']
        username = lead['channel_username']
        logging.info(f"Scraping @{username} details...")
        
        try:
            # 1. Fetch channel full details
            entity = await client.get_input_entity(username)
            full_channel = await client(GetFullChannelRequest(channel=entity))
            description = full_channel.full_chat.about or ""
            
            # 2. Fetch latest 20 messages
            messages_list = []
            async for msg in client.iter_messages(entity, limit=20):
                if msg.text:
                    messages_list.append(msg.text)
            sample_text = " \n ".join(messages_list)
            
            # 3. Extract contacts using upgraded logic
            contacts = extract_contacts_local(sample_text, description, username)
            
            contact_username = contacts.get('contact_username')
            whatsapp = contacts.get('whatsapp')
            website = contacts.get('website')
            
            if contact_username or whatsapp or website:
                logging.info(f"🎉 Resolved contacts for @{username}: Contact=@{contact_username}, WA={whatsapp}, Web={website}")
                cur.execute("""
                    UPDATE leads 
                    SET contact_username = COALESCE(NULLIF(contact_username, ''), %s),
                        whatsapp = COALESCE(NULLIF(whatsapp, ''), %s),
                        website = COALESCE(NULLIF(website, ''), %s)
                    WHERE id = %s
                """, (contact_username, whatsapp, website, lead_id))
                conn.commit()
                updated_count += 1
            else:
                logging.info(f"No contacts found for @{username}.")
                
            # Add short delay to prevent Telegram rate limit trigger
            await asyncio.sleep(2)

        except Exception as e:
            logging.error(f"Error scraping @{username}: {e}")
            await asyncio.sleep(2)

    cur.close()
    conn.close()
    await tg_manager.disconnect_all()
    logging.info(f"Contact Resolution completed. Updated contact details for {updated_count} channels.")

if __name__ == "__main__":
    asyncio.run(main())
