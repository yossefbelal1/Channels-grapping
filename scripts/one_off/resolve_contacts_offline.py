import os
import sys
import re
import logging
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

load_dotenv()

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

def main():
    logging.info("Starting Offline Contact Resolution...")
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Select leads without contact_username
    cur.execute("""
        SELECT id, channel_username, description 
        FROM leads 
        WHERE (contact_username IS NULL OR contact_username = '')
          AND status != 'rejected'
    """)
    leads = cur.fetchall()
    logging.info(f"Loaded {len(leads)} leads lacking contact usernames from DB.")
    
    updated_count = 0
    
    for lead in leads:
        lead_id = lead['id']
        username = lead['channel_username']
        description = lead['description'] or ""
        
        # Load latest 30 posts from DB
        cur.execute("""
            SELECT message_text 
            FROM channel_posts 
            WHERE channel_username = %s 
            ORDER BY timestamp DESC 
            LIMIT 30
        """, (username,))
        posts = cur.fetchall()
        posts_text = " \n ".join([p['message_text'] for p in posts if p['message_text']])
        
        contacts = extract_contacts_local(posts_text, description, username)
        
        c_user = contacts.get('contact_username')
        c_wa = contacts.get('whatsapp')
        c_web = contacts.get('website')
        
        if c_user or c_wa or c_web:
            logging.info(f"Resolved contacts for @{username} offline: Contact=@{c_user}, WA={c_wa}, Web={c_web}")
            cur.execute("""
                UPDATE leads 
                SET contact_username = COALESCE(NULLIF(contact_username, ''), %s),
                    whatsapp = COALESCE(NULLIF(whatsapp, ''), %s),
                    website = COALESCE(NULLIF(website, ''), %s)
                WHERE id = %s
            """, (c_user, c_wa, c_web, lead_id))
            updated_count += 1
            
    conn.commit()
    cur.close()
    conn.close()
    logging.info(f"Offline Contact Resolution completed. Updated contact details for {updated_count} leads.")

if __name__ == "__main__":
    main()
