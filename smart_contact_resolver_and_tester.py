"""
Smart Contact Resolver & Simulation Tester.
1. Diagnoses all campaign log failures and pending items.
2. Cleans malformed contact_usernames (e.g. trailing underscores, glued words like 'whatsup').
3. Re-extracts contacts from channel descriptions and message posts (supports t.me/ and @ mentions).
4. Tests resolving entities live using user_session to verify valid Telegram users.
5. Updates the database with verified contacts and resets fixed failures to 'pending'.
"""
import asyncio
import sys
import os
import re
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from telethon import TelegramClient, errors

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from tg_manager import get_session_path

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "dbname": os.getenv("DB_NAME", "leadhunter"),
    "user": os.getenv("DB_USER", "leadhunter"),
    "password": os.getenv("DB_PASSWORD", "leadhunter"),
}

CAMPAIGN_ID_PREFIX = "30d91eeb"

def clean_candidate_username(raw_u: str) -> str:
    """Cleans up raw username string from common artifacts."""
    if not raw_u:
        return ""
    u = raw_u.strip().lstrip('@').lstrip('/').rstrip('.,;:)!?*~`"\'')
    
    # Strip common glued words at the end
    glued_suffixes = ['whatsup', 'whatsapp', 'telegram', 'tele', 'vipsignal', 'channel', 'group']
    for suffix in glued_suffixes:
        if u.lower().endswith(suffix) and len(u) > len(suffix) + 3:
            u = u[:-len(suffix)]
            break
            
    # Strip trailing underscores if not part of a legitimate name or if hanging
    while u.endswith('_') and len(u) > 3:
        u = u[:-1]
    while u.startswith('_') and len(u) > 3:
        u = u[1:]
        
    return u.strip()

def extract_potential_contacts(channel_username: str, description: str, posts: list) -> list:
    """Extracts candidate contact usernames from description and post text."""
    combined = (description or "") + "\n" + "\n".join(posts)
    
    # Pattern 1: Contact keyword followed by @username or t.me/username
    keywords = (
        r'للتواصل|تواصل|راسل|مراسلة|للاشتراك|اشتراك|الادارة|ادارة|المشرف|مشرف|الدعم|دعم|'
        r'المسؤول|مسؤول|استفسار|خاص|الخاص|كلمني|مالك|صاحب|'
        r'admin|support|contact|owner|manager|ceo|dm|pm|help|inquiry'
    )
    
    candidates = []
    
    # High priority: keyword -> link/mention
    fwd_matches = re.finditer(r'(?:' + keywords + r')\s*[:\-\x20]{1,10}(?:https?://)?(?:t\.me/|@)([a-zA-Z0-9_]{3,35})', combined, re.IGNORECASE)
    for m in fwd_matches:
        cand = clean_candidate_username(m.group(1))
        if cand and cand.lower() != channel_username.lower() and cand not in candidates:
            candidates.append(cand)
            
    # Pattern 2: link/mention -> keyword
    bwd_matches = re.finditer(r'(?:https?://)?(?:t\.me/|@)([a-zA-Z0-9_]{3,35})\s*[:\-\x20]{1,10}(?:' + keywords + r')', combined, re.IGNORECASE)
    for m in bwd_matches:
        cand = clean_candidate_username(m.group(1))
        if cand and cand.lower() != channel_username.lower() and cand not in candidates:
            candidates.append(cand)
            
    # Pattern 3: Any t.me/username link
    tme_matches = re.finditer(r'(?:https?://)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]{3,35})', combined, re.IGNORECASE)
    skip_tme = {'joinchat', 'addstickers', 'share', 'channel', 'vip', 'forex', 'crypto', 'trading', 'signals', 'bot', 'adminbot'}
    for m in tme_matches:
        cand = clean_candidate_username(m.group(1))
        if cand and cand.lower() != channel_username.lower() and cand.lower() not in skip_tme and not cand.startswith('+') and cand not in candidates:
            candidates.append(cand)
            
    # Pattern 4: Any @mention in description
    if description:
        desc_mentions = re.finditer(r'@([a-zA-Z0-9_]{3,35})', description)
        for m in desc_mentions:
            cand = clean_candidate_username(m.group(1))
            if cand and cand.lower() != channel_username.lower() and cand.lower() not in skip_tme and cand not in candidates:
                candidates.append(cand)

    return candidates

async def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT id, message_text FROM campaigns WHERE id::text LIKE %s LIMIT 1", (CAMPAIGN_ID_PREFIX + '%',))
    row = cur.fetchone()
    if not row:
        print("Campaign not found!")
        return
    campaign_id = row['id']
    print(f"=== CAMPAIGN: {campaign_id} ===")

    # Connect Telethon client for resolution simulation
    session_path = get_session_path("user_session")
    client = TelegramClient(session_path, 36318125, '5f2ea025376141a257979750c3fc9cf7')
    await client.connect()
    if not await client.is_user_authorized():
        print("Telegram Client is NOT authorized!")
        await client.disconnect()
        return

    me = await client.get_me()
    print(f"Connected as: {me.first_name} (@{me.username}) | ID: {me.id}\n")

    # Step 1: Fix bad usernames in leads table (e.g. trailing underscores)
    cur.execute("""
        SELECT cl.id as log_id, l.id as lead_id, l.channel_username, l.contact_username, cl.error_message
        FROM campaign_logs cl
        JOIN leads l ON l.id = cl.lead_id
        WHERE cl.campaign_id = %s
          AND cl.status IN ('failed', 'FAILED', 'error', 'ERROR')
          AND cl.error_message NOT ILIKE '%%No owner or admin contact%%'
          AND cl.error_message NOT ILIKE '%%too many%%'
    """, (campaign_id,))
    bad_syntax_leads = cur.fetchall()
    print(f"--- STEP 1: FIXING MALFORMED CONTACT USERNAMES ({len(bad_syntax_leads)} candidates) ---")
    
    fixed_syntax_count = 0
    for item in bad_syntax_leads:
        raw_contact = item['contact_username'] or ''
        cleaned = clean_candidate_username(raw_contact)
        if cleaned and cleaned != raw_contact:
            # Test resolving via Telethon
            try:
                entity = await client.get_entity(cleaned)
                if getattr(entity, 'id', None):
                    print(f"  [FIXED & RESOLVED] @{item['channel_username']} | Old: @{raw_contact} -> Clean: @{cleaned} (Name: {getattr(entity, 'first_name', '')})")
                    cur.execute("UPDATE leads SET contact_username = %s WHERE id = %s", (cleaned, item['lead_id']))
                    cur.execute("UPDATE campaign_logs SET status = 'pending', error_message = NULL, sent_at = NULL WHERE id = %s", (item['log_id'],))
                    conn.commit()
                    fixed_syntax_count += 1
            except Exception as e:
                pass
    print(f"Total syntax-repaired and verified: {fixed_syntax_count}\n")

    # Step 2: Recover contacts for the 255 "No owner or admin contact" leads
    cur.execute("""
        SELECT cl.id as log_id, l.id as lead_id, l.channel_username, l.description, l.member_count
        FROM campaign_logs cl
        JOIN leads l ON l.id = cl.lead_id
        WHERE cl.campaign_id = %s
          AND cl.status IN ('failed', 'FAILED', 'error', 'ERROR')
          AND cl.error_message ILIKE '%%No owner or admin contact%%'
        ORDER BY l.member_count DESC NULLS LAST
    """, (campaign_id,))
    no_contact_leads = cur.fetchall()
    print(f"--- STEP 2: RE-EXTRACTING CONTACTS FOR {len(no_contact_leads)} NO-CONTACT CHANNELS ---")

    recovered_count = 0
    for lead in no_contact_leads:
        channel_uname = lead['channel_username'] or ''
        desc = lead['description'] or ''
        
        # Get posts from DB
        cur.execute("""
            SELECT message_text FROM channel_posts
            WHERE channel_username = %s
            ORDER BY timestamp DESC
            LIMIT 20
        """, (channel_uname,))
        posts = [p['message_text'] or '' for p in cur.fetchall()]
        
        candidates = extract_potential_contacts(channel_uname, desc, posts)
        
        valid_contact = None
        for cand in candidates:
            # Check candidate
            try:
                cand_clean = clean_candidate_username(cand)
                if len(cand_clean) < 4:
                    continue
                ent = await client.get_entity(cand_clean)
                if ent and getattr(ent, 'id', None):
                    valid_contact = cand_clean
                    first_name = getattr(ent, 'first_name', '')
                    print(f"  [RECOVERED] Channel @{channel_uname:25s} ({lead['member_count'] or 0:,} members) -> Contact: @{valid_contact} ({first_name})")
                    break
            except Exception:
                continue
                
        if valid_contact:
            cur.execute("UPDATE leads SET contact_username = %s WHERE id = %s", (valid_contact, lead['lead_id']))
            cur.execute("UPDATE campaign_logs SET status = 'pending', error_message = NULL, sent_at = NULL WHERE id = %s", (lead['log_id'],))
            conn.commit()
            recovered_count += 1

    print(f"\nTotal no-contact channels recovered & verified: {recovered_count} / {len(no_contact_leads)}\n")

    # Step 3: Run comprehensive Simulation Test on pending leads
    cur.execute("""
        SELECT cl.id as log_id, l.id as lead_id, l.channel_username, l.contact_username
        FROM campaign_logs cl
        JOIN leads l ON l.id = cl.lead_id
        WHERE cl.campaign_id = %s
          AND cl.status = 'pending'
        ORDER BY l.member_count DESC NULLS LAST
        LIMIT 10
    """, (campaign_id,))
    pending_sample = cur.fetchall()

    print("--- STEP 3: SIMULATION TEST (Testing entity input resolution on pending queue) ---")
    sim_success = 0
    sim_total = len(pending_sample)
    for item in pending_sample:
        target = item['contact_username']
        channel = item['channel_username']
        try:
            input_entity = await client.get_input_entity(target)
            print(f"  [SIM OK] @{channel:25s} -> Target: @{target:25s} (InputEntity resolved: {input_entity.__class__.__name__})")
            sim_success += 1
        except Exception as e:
            print(f"  [SIM FAIL] @{channel:25s} -> Target: @{target:25s} (Error: {e})")

    print(f"\nSimulation Result: {sim_success}/{sim_total} sample contacts successfully resolved!")

    # Final breakdown
    cur.execute("""
        SELECT status, COUNT(*) as cnt
        FROM campaign_logs
        WHERE campaign_id = %s
        GROUP BY status
        ORDER BY cnt DESC
    """, (campaign_id,))
    print("\n=== FINAL UPDATED STATUS BREAKDOWN ===")
    for r in cur.fetchall():
        print(f"  {r['status']:10s}: {r['cnt']}")

    await client.disconnect()
    conn.close()
    print("\nAll done!")

if __name__ == "__main__":
    asyncio.run(main())
