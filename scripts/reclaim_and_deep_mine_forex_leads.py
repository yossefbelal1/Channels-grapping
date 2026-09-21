import asyncio
import logging
import os
import re
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor
from telethon import TelegramClient, errors
from telethon.tl.types import User, Channel, Chat
from telethon.tl.functions.channels import GetFullChannelRequest, GetChannelRecommendationsRequest

from app.validator.contact_extractor import extract_contacts, _is_bot, JUNK_USERNAMES

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

DB_PARAMS = {
    'dbname': os.getenv('DB_NAME', 'leadhunter_db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'leadhunter_pass'),
    'host': os.getenv('DB_HOST', 'postgres'),
    'port': int(os.getenv('DB_PORT', '5432'))
}

API_ID = 39064636
API_HASH = '72d90d8ac46e9293e3d5254d9645e4f9'
SESSION_PATH = '/app/sessions/reclaim_worker_session'

CONTACT_TRIGGERS_REGEX = re.compile(
    r'(?:تواصل|راسل|اشتراك|للاشتراك|الدعم|الادارة|الإدارة|خاص|الخاص|واتساب|whatsapp|wa\.me|vip|توصيات)',
    re.IGNORECASE
)

async def resolve_and_verify_user(client: TelegramClient, username: str, depth: int = 0) -> tuple[str | None, str | None]:
    """
    Resolves a username. If it is a User, returns (username, None).
    If it is a Channel and depth < 2, recursively inspects the channel's about & pinned
    to locate the actual human user behind it.
    """
    if not username or depth > 2:
        return None, None
    clean = username.strip().lstrip('@')
    if clean.lower() in JUNK_USERNAMES or _is_bot(clean):
        return None, None

    try:
        ent = await asyncio.wait_for(client.get_entity(clean), timeout=8.0)
        if isinstance(ent, User):
            if getattr(ent, 'bot', False):
                return None, None
            return getattr(ent, 'username', clean), None
        elif isinstance(ent, (Channel, Chat)):
            # Secondary channel! Inspect it to find the real person!
            logging.info(f"Candidate @{clean} is a secondary Channel. Recursively inspecting for human contact...")
            full = await asyncio.wait_for(client(GetFullChannelRequest(ent)), timeout=8.0)
            about = getattr(full.full_chat, 'about', '') or ''
            pinned_id = getattr(full.full_chat, 'pinned_msg_id', None)
            pinned_text = ''
            if pinned_id:
                try:
                    p_msg = await asyncio.wait_for(client.get_messages(ent, ids=pinned_id), timeout=8.0)
                    if p_msg and p_msg.message:
                        pinned_text = p_msg.message
                except Exception:
                    pass
            contacts = extract_contacts(text="", description=about, channel_username=clean, pinned_text=pinned_text)
            cand = contacts.get('contact_username') or contacts.get('owner_username') or contacts.get('admin_username')
            if cand and cand.lower() != clean.lower():
                return await resolve_and_verify_user(client, cand, depth + 1)
            # Also check whatsapp
            wa = contacts.get('whatsapp')
            return None, wa
    except Exception as e:
        logging.debug(f"Could not resolve candidate @{clean}: {e}")
        return None, None

async def inspect_and_reclaim_channel(client: TelegramClient, conn, channel_username: str, lead_id: str, campaign_id: str | None):
    cur = conn.cursor(cursor_factory=RealDictCursor)
    clean_ch = channel_username.strip().lstrip('@')
    
    try:
        entity = await asyncio.wait_for(client.get_entity(clean_ch), timeout=10.0)
        if not isinstance(entity, (Channel, Chat)):
            logging.info(f"Skipping non-channel @{clean_ch}")
            return
            
        title = getattr(entity, 'title', '') or ''
        full = await asyncio.wait_for(client(GetFullChannelRequest(entity)), timeout=10.0)
        full_chat = full.full_chat
        about = getattr(full_chat, 'about', '') or ''
        members = getattr(full_chat, 'participants_count', 0) or 0
        pinned_id = getattr(full_chat, 'pinned_msg_id', None)
        
        pinned_text = ""
        if pinned_id:
            try:
                p_msg = await asyncio.wait_for(client.get_messages(entity, ids=pinned_id), timeout=8.0)
                if p_msg and p_msg.message:
                    pinned_text = p_msg.message
            except Exception as pe:
                logging.debug(f"Failed to fetch pinned message for @{clean_ch}: {pe}")

        # Fetch recent 40 messages to search for high-intent contact posts
        recent_posts_text = []
        try:
            msgs = await asyncio.wait_for(client.get_messages(entity, limit=40), timeout=10.0)
            for m in msgs:
                if m.message and CONTACT_TRIGGERS_REGEX.search(m.message):
                    recent_posts_text.append(m.message)
        except Exception as me:
            logging.debug(f"Failed to fetch recent messages for @{clean_ch}: {me}")
            
        combined_recent = "\n---\n".join(recent_posts_text)
        
        # Run enhanced contact extraction
        contacts = extract_contacts(
            text=combined_recent,
            description=about,
            channel_username=clean_ch,
            pinned_text=pinned_text
        )
        
        raw_contact = contacts.get('contact_username') or contacts.get('owner_username') or contacts.get('admin_username') or contacts.get('analyst_username')
        whatsapp = contacts.get('whatsapp')
        
        verified_user = None
        if raw_contact and raw_contact.lower() != clean_ch.lower():
            verified_user, wa_sub = await resolve_and_verify_user(client, raw_contact)
            if wa_sub and not whatsapp:
                whatsapp = wa_sub

        # Check if forex / trading
        is_forex = bool(re.search(r'ذهب|فوركس|تداول|عملات|crypto|forex|gold|trade|توصيات|xauusd|صفقات|تحليل', f"{title} {about} {pinned_text}", re.IGNORECASE))
        
        logging.info(f"[@{clean_ch}] Title='{title[:30]}' Members={members} Forex={is_forex} Contact=@{verified_user} WhatsApp={whatsapp}")
        
        # Determine priority and tier
        tier = 'Tier_A' if members >= 10000 else 'Tier_B'
        priority = 'P0' if (members >= 15000 or (tier == 'Tier_A' and is_forex)) else 'P1'
        priority_score = 99 if priority == 'P0' else 95
        
        if verified_user:
            # Update leads table
            cur.execute("""
                UPDATE leads
                SET title = CASE WHEN %s != '' THEN %s ELSE title END,
                    description = CASE WHEN %s != '' THEN %s ELSE description END,
                    member_count = GREATEST(member_count, %s),
                    contact_username = %s,
                    admin_username = %s,
                    whatsapp = COALESCE(%s, whatsapp),
                    forex_intent_score = CASE WHEN %s THEN GREATEST(forex_intent_score, 90) ELSE forex_intent_score END,
                    lead_score = GREATEST(lead_score, %s),
                    tier = %s,
                    outreach_priority = %s,
                    outreach_priority_score = %s,
                    outreach_priority_reason = %s,
                    status = 'new',
                    last_scan = NOW()
                WHERE id = %s;
            """, (title, title, about, about, members, verified_user, verified_user, whatsapp, is_forex, priority_score, tier, priority, priority_score, f"Deep Scan Verified: @{verified_user}", lead_id))
            
            # Update campaign_logs to approved
            cur.execute("""
                UPDATE campaign_logs
                SET status = 'approved',
                    priority = %s,
                    priority_score = %s,
                    priority_reason = %s,
                    eligibility = 'ELIGIBLE',
                    error_message = NULL,
                    last_error = NULL,
                    account_used = NULL,
                    sent_at = NULL
                WHERE lead_id = %s;
            """, (priority, priority_score, f"Deep Scan Verified: @{verified_user}", lead_id))
            
            conn.commit()
            logging.info(f"✅ RESCUED & APPROVED: @{clean_ch} -> Contact: @{verified_user} ({priority})")
        else:
            # Update basic metadata in leads anyway
            cur.execute("""
                UPDATE leads
                SET title = CASE WHEN %s != '' THEN %s ELSE title END,
                    description = CASE WHEN %s != '' THEN %s ELSE description END,
                    member_count = GREATEST(member_count, %s),
                    whatsapp = COALESCE(%s, whatsapp),
                    last_scan = NOW()
                WHERE id = %s;
            """, (title, title, about, about, members, whatsapp, lead_id))
            conn.commit()

        # Channel Discovery: Similar channels harvest
        try:
            recs = await client(GetChannelRecommendationsRequest(channel=entity))
            if recs and recs.chats:
                new_recs = 0
                for rec_chat in recs.chats:
                    rec_uname = getattr(rec_chat, 'username', None)
                    if rec_uname:
                        rec_clean = rec_uname.strip().lstrip('@')
                        rec_title = getattr(rec_chat, 'title', '')
                        # Check if exists
                        cur.execute("SELECT 1 FROM leads WHERE channel_username ILIKE %s UNION SELECT 1 FROM seed_channels WHERE channel_username ILIKE %s", (rec_clean, rec_clean))
                        if not cur.fetchone():
                            cur.execute("""
                                INSERT INTO seed_channels (id, channel_username, source, notes, created_at, processed)
                                VALUES (%s, %s, 'telegram_recommendations', %s, NOW(), false)
                                ON CONFLICT DO NOTHING;
                            """, (str(uuid.uuid4()), rec_clean, f"Recommended by @{clean_ch} ({rec_title})"))
                            new_recs += 1
                if new_recs > 0:
                    conn.commit()
                    logging.info(f"🌟 Discovered {new_recs} new similar channels from @{clean_ch}")
        except Exception as rec_err:
            logging.debug(f"Recommendations error for @{clean_ch}: {rec_err}")

    except errors.FloodWaitError as fwe:
        logging.warning(f"FloodWait encountered: {fwe.seconds}s. Sleeping...")
        await asyncio.sleep(fwe.seconds + 5)
    except Exception as e:
        logging.warning(f"Error inspecting @{clean_ch}: {e}")
    finally:
        cur.close()

async def main():
    conn = psycopg2.connect(**DB_PARAMS)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT DISTINCT l.id as lead_id, l.channel_username, cl.campaign_id, cl.status as campaign_status,
               cl.error_message, l.member_count, l.title
        FROM campaign_logs cl
        JOIN leads l ON cl.lead_id = l.id
        WHERE cl.status IN ('skipped', 'failed', 'pending_review')
          AND (
            cl.error_message IN ('No contact username', 'Not eligible: Empty contact username')
            OR cl.error_message ILIKE '%admin privileges%'
            OR cl.error_message ILIKE '%Cannot find any entity%'
            OR cl.error_message ILIKE '%No user has%'
            OR l.contact_username IS NULL
            OR l.contact_username = ''
            OR LOWER(l.contact_username) = LOWER(l.channel_username)
          )
          AND l.channel_username IS NOT NULL
          AND l.channel_username != ''
          AND NOT l.channel_username LIKE 'private_%'
          AND l.channel_username NOT IN (
            'lilyforex11', 'MissGold21', 'private_2337975166', 'GorillaSignals0',
            'gorillatrading0', 'CryptoArabs1', 'tqcharts', 'forexomni', 'abo_shaqran'
          )
        ORDER BY l.member_count DESC NULLS LAST
        LIMIT 40;
    """)
    candidates = cur.fetchall()
    cur.close()
    
    print(f"=== Found {len(candidates)} high-priority candidate channels for reclamation ===", flush=True)
    
    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
    await client.connect()
    
    rescued_count = 0
    try:
        for idx, row in enumerate(candidates, 1):
            ch = row['channel_username']
            lid = row['lead_id']
            cid = row['campaign_id']
            print(f"\n[{idx}/{len(candidates)}] Inspecting @{ch} ({row['member_count']} members)...", flush=True)
            try:
                await inspect_and_reclaim_channel(client, conn, ch, lid, cid)
            except Exception as item_err:
                print(f"  -> Error processing @{ch}: {item_err}", flush=True)
            await asyncio.sleep(1.5)
    finally:
        await client.disconnect()
        conn.close()
        print("\n=== Deep Mining & Reclamation Sweep Complete! ===", flush=True)

if __name__ == '__main__':
    asyncio.run(main())
