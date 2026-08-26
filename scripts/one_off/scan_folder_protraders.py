"""
scan_folder_protraders.py
Scans all channels inside the Telegram folder "ProTraders✅" on the user_session account,
extracts owner/contact usernames, inserts them as leads, and auto-enqueues them
into the active campaign for automatic outreach.
"""
import os
import sys
import re
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
from telethon import TelegramClient
from telethon.tl.functions.messages import GetDialogFiltersRequest
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.types import DialogFilter, InputPeerChannel, InputPeerChat, InputPeerUser
from dotenv import load_dotenv

load_dotenv()

# ── Telegram credentials ──────────────────────────────────────────────────────
API_ID   = int(os.getenv("API_ID",   "32950512"))
API_HASH = os.getenv("API_HASH", "23f5be247297fe7645193f6f782dad67")
SESSION  = os.path.join("sessions", "user_session")

# ── Target folder name ────────────────────────────────────────────────────────
TARGET_FOLDER = "ProTraders"   # partial match, case-insensitive

# ── DB ────────────────────────────────────────────────────────────────────────
DB_CFG = dict(
    host     = os.getenv("DB_HOST", "localhost"),
    port     = int(os.getenv("DB_PORT", 5432)),
    dbname   = os.getenv("DB_NAME", "leadhunter_db"),
    user     = os.getenv("DB_USER", "postgres"),
    password = os.getenv("DB_PASSWORD", ""),
)

KEYWORDS = (
    r'للتواصل|تواصل|للاشتراك|اشتراك|للانضمام|انضمام|الادارة|الاداره|المشرف|الدعم|دعم|المسؤول|المسئول|'
    r'للاستفسار|استفسار|حسابي|خاص|راسلني|راسلنا|تواصل معي|راسلني على|ارسل لي|للتواصل مع|للتواصل عبر|'
    r'سجل|التسجيل|للتشراك|للتحدث|تحدث|مطور|المطور|'
    r'admin|administrator|support|contact|help|owner|manager|ceo|inquiry|subscribe|subscription|pm|dm|chat|personal|me'
)

def extract_contact(text: str, desc: str, ch_uname: str) -> str | None:
    SKIP = {
        'vip', 'premium', 'joinchat', 'channel', 'bot', 'ads', 'link', 'group', 'telegram', 
        'robot', 'signals', 'crypto', 'forex', 'arabic', 'trade', 'trading', 'chart', 'charts', 
        'alerts', 'alert', 'course', 'courses', 'education', 'academy', 'hub', 'capital', 'fund', 
        'fx', 'gold', 'signal', 'goldfx', 'team', 'club', 'official', 'news', 'fxsignals', 'system',
        'user', 'adminbot', 'helper', 'supportbot', 'channelbot'
    }
    for src in [desc or '', text or '']:
        # keyword before @
        m = re.search(r'(?:' + KEYWORDS + r')\s*[:\-\s]*@([a-zA-Z0-9_]{5,32})', src, re.I)
        if m and m.group(1).lower() not in SKIP and m.group(1).lower() != ch_uname.lower():
            return m.group(1)
        # @ before keyword
        m = re.search(r'@([a-zA-Z0-9_]{5,32})\s*[:\-\s]*(?:' + KEYWORDS + r')', src, re.I)
        if m and m.group(1).lower() not in SKIP and m.group(1).lower() != ch_uname.lower():
            return m.group(1)
        # fallback: first @mention that isn't the channel itself and isn't in SKIP
        for u in re.findall(r'@([a-zA-Z0-9_]{5,32})', src):
            if u.lower() not in SKIP and u.lower() != ch_uname.lower():
                return u
    return None

# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    print(f"\n{'='*55}")
    print(f"  ProTraders Folder Scanner & Auto-Outreach Enqueuer")
    print(f"{'='*55}\n")

    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        print("[!] user_session is not authorized. Run login.py first.")
        return

    me = await client.get_me()
    print(f"[+] Connected as @{me.username or me.first_name}")

    # ── Step 1: fetch all channels/groups in the account (active + archived) ──
    print(f"\n[*] Fetching all active dialogs on this account...")
    dialogs_active = await client.get_dialogs(limit=None)
    
    print(f"[*] Fetching all archived dialogs on this account...")
    dialogs_archived = []
    try:
        dialogs_archived = await client.get_dialogs(limit=None, folder=1)
    except Exception as arch_err:
        print(f"    [!] Could not retrieve archived dialogs: {arch_err}")
        
    dialogs = dialogs_active + dialogs_archived
    channels = [d for d in dialogs if d.is_channel or d.is_group]

    print(f"\n[+] Total unique channels to scan: {len(channels)}\n")

    # ── Step 2: connect to DB ─────────────────────────────────────────────────
    conn = psycopg2.connect(**DB_CFG)
    conn.autocommit = True
    cur  = conn.cursor(cursor_factory=RealDictCursor)

    # Load auto campaign ID
    auto_campaign_id = None
    try:
        cid_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'auto_campaign_id.txt')
        if os.path.exists(cid_file):
            with open(cid_file) as f:
                auto_campaign_id = f.read().strip()
            print(f"[+] Auto campaign ID: {auto_campaign_id}\n")
    except Exception:
        pass

    # ── Step 3: scan each channel ─────────────────────────────────────────────
    new_added = updated = enqueued = failed = 0

    for idx, d in enumerate(channels, 1):
        entity    = d.entity
        has_uname = getattr(entity, 'username', None)
        ch_uname  = entity.username if has_uname else f"private_{entity.id}"
        print(f"[{idx:>3}/{len(channels)}] @{ch_uname} — {d.name}")

        # check DB
        cur.execute("SELECT id, contact_username FROM leads WHERE channel_username = %s", (ch_uname,))
        existing = cur.fetchone()
        if existing and existing['contact_username']:
            print(f"         ✓ Already has contact @{existing['contact_username']} — skipping scrape")
            # still enqueue if missing from campaign
            if auto_campaign_id:
                cur.execute("""
                    INSERT INTO campaign_logs (id, campaign_id, lead_id, status)
                    SELECT gen_random_uuid(), %s, %s, 'pending'
                    WHERE NOT EXISTS (
                        SELECT 1 FROM campaign_logs WHERE campaign_id=%s AND lead_id=%s
                    )
                """, (auto_campaign_id, existing['id'], auto_campaign_id, existing['id']))
                if cur.rowcount > 0:
                    enqueued += 1
                    print(f"         → Enqueued for outreach!")
            continue

        # scrape description, pinned message, and recent posts
        about = ''
        posts_text_list = []
        member_count = getattr(entity, 'participants_count', 0) or 0
        try:
            full = await client(GetFullChannelRequest(entity))
            about = full.full_chat.about or ''
            member_count = full.full_chat.participants_count or member_count
            
            # Fetch pinned message text
            if getattr(full.full_chat, 'pinned_msg_id', None):
                try:
                    pinned_msg = await client.get_messages(entity, ids=full.full_chat.pinned_msg_id)
                    if pinned_msg and pinned_msg.message:
                        posts_text_list.append(pinned_msg.message)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            msgs = await client.get_messages(entity, limit=100)
            for m in msgs:
                if m.message:
                    posts_text_list.append(m.message)
        except Exception:
            pass

        posts_text = ' \n '.join(posts_text_list)

        contact = extract_contact(posts_text, about, ch_uname)
        print(f"         → contact: @{contact}" if contact else "         → no contact found")

        # upsert lead
        try:
            cur_plain = conn.cursor()
            cur_plain.execute("""
                INSERT INTO leads (
                    channel_username, member_count, contact_username,
                    status, forex_category, forex_intent_score, lead_score,
                    tier, is_group, description, language, last_scan, last_activity
                ) VALUES (
                    %s,%s,%s,'new','unknown',80,50,'Tier_D',%s,%s,'Arabic',NOW(),NOW()
                )
                ON CONFLICT (channel_username) DO UPDATE SET
                    contact_username = COALESCE(NULLIF(leads.contact_username,''), EXCLUDED.contact_username),
                    member_count     = GREATEST(leads.member_count, EXCLUDED.member_count),
                    description      = COALESCE(NULLIF(leads.description,''), EXCLUDED.description),
                    language         = COALESCE(NULLIF(leads.language,''), 'Arabic'),
                    last_scan        = COALESCE(leads.last_scan, NOW()),
                    last_activity    = NOW()
            """, (ch_uname, member_count, contact, d.is_group, about))
            cur_plain.close()

            if existing:
                updated += 1
            else:
                new_added += 1

            # fetch lead id then enqueue
            if contact and auto_campaign_id:
                cur.execute("SELECT id FROM leads WHERE channel_username=%s", (ch_uname,))
                lead_row = cur.fetchone()
                if lead_row:
                    cur_plain2 = conn.cursor()
                    cur_plain2.execute("""
                        INSERT INTO campaign_logs (id, campaign_id, lead_id, status)
                        SELECT gen_random_uuid(), %s, %s, 'pending'
                        WHERE NOT EXISTS (
                            SELECT 1 FROM campaign_logs WHERE campaign_id=%s AND lead_id=%s
                        )
                    """, (auto_campaign_id, lead_row['id'], auto_campaign_id, lead_row['id']))
                    if cur_plain2.rowcount > 0:
                        enqueued += 1
                        print(f"         ✅ Enqueued for outreach → @{contact}")
                    cur_plain2.close()
        except Exception as db_err:
            print(f"         [!] DB error: {db_err}")
            failed += 1

        await asyncio.sleep(1.5)

    cur.close()
    conn.close()
    await client.disconnect()

    print(f"\n{'='*55}")
    print(f"  SCAN COMPLETE")
    print(f"  Channels scanned   : {len(channels)}")
    print(f"  New leads added    : {new_added}")
    print(f"  Existing updated   : {updated}")
    print(f"  Enqueued for send  : {enqueued}")
    print(f"  Errors             : {failed}")
    print(f"{'='*55}")
    print(f"\nThe campaign dispatcher will now send the outreach message")
    print(f"to all {enqueued} newly enqueued contacts automatically!\n")

if __name__ == "__main__":
    asyncio.run(main())
