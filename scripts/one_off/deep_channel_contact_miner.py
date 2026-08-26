"""
Deep Channel Contact Miner.
For all channels in campaign_logs that failed with 'No contact' or are missing contacts:
1. Connects to Telegram via Telethon user_session.
2. Resolves channel entity and fetches FullChannel metadata:
   - Full About / Bio description
   - Pinned message text
3. Fetches up to 300 recent messages and scans:
   - Message text & captions
   - Inline Keyboard URL buttons (e.g. "تواصل مع الإدارة" buttons)
   - Contact keywords (Arabic + English)
   - Pinned announcements
4. Validates discovered usernames in real-time.
5. Updates leads table and moves campaign_logs to 'pending' for immediate outreach.
"""
import asyncio
import sys
import os
import re
import psycopg2
from psycopg2.extras import RealDictCursor
from telethon import TelegramClient, errors
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.types import Channel, MessageMediaContact, ReplyInlineMarkup, KeyboardButtonUrl

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

SKIP_USERNAMES = {
    'vip', 'premium', 'joinchat', 'channel', 'bot', 'ads', 'link', 'group', 'telegram', 
    'robot', 'signals', 'crypto', 'forex', 'arabic', 'trade', 'trading', 'chart', 'charts', 
    'alerts', 'alert', 'course', 'courses', 'education', 'academy', 'hub', 'capital', 'fund', 
    'fx', 'gold', 'signal', 'goldfx', 'team', 'club', 'official', 'news', 'fxsignals', 'system',
    'user', 'adminbot', 'helper', 'supportbot', 'channelbot', 'addstickers', 'share', 'instagram',
    'facebook', 'twitter', 'tiktok', 'youtube', 'whatsapp', 'website', 'binance', 'bybit', 'exness'
}

CONTACT_KEYWORDS = (
    r'للتواصل|تواصل|تواصلوا|راسل|راسلونا|راسلني|راسلنا|مراسلة|للمراسلة|'
    r'للاشتراك|اشتراك|للانضمام|انضمام|الادارة|الاداره|ادارة|اداره|'
    r'المشرف|مشرف|المشرفين|الدعم|دعم|المسؤول|المسئول|مسؤول|مسئول|'
    r'للاستفسار|استفسار|استفسارات|للاستفسارات|حسابي|خاص|الخاص|'
    r'تواصل معي|تواصل معنا|للتواصل معي|للتواصل معنا|راسلني على|راسلنا على|'
    r'ارسل لي|ارسل لنا|ارسل رسالة|كلمني|كلمني على|تواصل عبر|تواصلوا عبر|'
    r'سجل|التسجيل|للتشراك|للتحدث|تحدث|مطور|المطور|مطورين|'
    r'صاحب القناة|صاحب القناه|مالك القناة|مالك القناه|صاحب|مالك|المالك|الصاحب|'
    r'حساب الأدمن|حساب الادمن|الأدمن|الادمن|'
    r'admin|administrator|support|contact|help|owner|manager|ceo|founder|creator|'
    r'inquiry|inquiries|subscribe|subscription|pm|dm|chat|personal|me|contactme|contactus|'
    r'messageme|reachme|reachus|writeme|writeus|askme|tg|tele|telegram'
)

def clean_username(raw: str) -> str:
    if not raw:
        return ""
    u = raw.strip().lstrip('@').lstrip('/').rstrip('.,;:)!?*~`"\'')
    # strip url prefix if present
    u = re.sub(r'^https?://(?:www\.)?(?:t\.me|telegram\.me)/', '', u, flags=re.IGNORECASE)
    u = u.strip().lstrip('@').rstrip('/')
    
    for glued in ['whatsup', 'whatsapp', 'telegram', 'tele', 'vipsignal', 'channel', 'group']:
        if u.lower().endswith(glued) and len(u) > len(glued) + 3:
            u = u[:-len(glued)]
            break
            
    while u.endswith('_') and len(u) > 3:
        u = u[:-1]
    while u.startswith('_') and len(u) > 3:
        u = u[1:]
    return u.strip()

def extract_candidates_from_text(text: str, channel_username: str) -> list:
    if not text:
        return []
    
    candidates = []
    
    # 1. High priority: keyword followed by @ or t.me
    fwd = re.finditer(r'(?:' + CONTACT_KEYWORDS + r')\s*[:\-\x20]{1,10}(?:https?://)?(?:t\.me/|@)([a-zA-Z0-9_]{3,35})', text, re.IGNORECASE)
    for m in fwd:
        cand = clean_username(m.group(1))
        if cand and cand.lower() != channel_username.lower() and cand.lower() not in SKIP_USERNAMES and not cand.startswith('+'):
            if cand not in candidates:
                candidates.append(cand)
                
    # 2. link/mention followed by keyword
    bwd = re.finditer(r'(?:https?://)?(?:t\.me/|@)([a-zA-Z0-9_]{3,35})\s*[:\-\x20]{1,10}(?:' + CONTACT_KEYWORDS + r')', text, re.IGNORECASE)
    for m in bwd:
        cand = clean_username(m.group(1))
        if cand and cand.lower() != channel_username.lower() and cand.lower() not in SKIP_USERNAMES and not cand.startswith('+'):
            if cand not in candidates:
                candidates.append(cand)
                
    # 3. Any explicit t.me/username link
    tme = re.finditer(r'(?:https?://)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]{3,35})', text, re.IGNORECASE)
    for m in tme:
        cand = clean_username(m.group(1))
        if cand and cand.lower() != channel_username.lower() and cand.lower() not in SKIP_USERNAMES and not cand.startswith('+'):
            if cand not in candidates:
                candidates.append(cand)
                
    # 4. Any @mention
    at_matches = re.finditer(r'@([a-zA-Z0-9_]{3,35})', text)
    for m in at_matches:
        cand = clean_username(m.group(1))
        if cand and cand.lower() != channel_username.lower() and cand.lower() not in SKIP_USERNAMES and not cand.startswith('+'):
            if cand not in candidates:
                candidates.append(cand)

    return candidates

async def mine_channel(client: TelegramClient, channel_username: str) -> str:
    """Deeply inspects a channel to extract and verify the owner/admin contact."""
    try:
        entity = await client.get_entity(channel_username)
        if not isinstance(entity, Channel):
            return None
    except Exception as e:
        return None

    all_candidates = []

    # A. Check FullChannel (About description + Pinned message)
    try:
        full = await client(GetFullChannelRequest(channel=entity))
        about = getattr(full.full_chat, 'about', '') or ''
        about_cands = extract_candidates_from_text(about, channel_username)
        all_candidates.extend(about_cands)

        # Check pinned message
        pinned_msg_id = getattr(full.full_chat, 'pinned_msg_id', None)
        if pinned_msg_id:
            try:
                pinned_msg = await client.get_messages(entity, ids=pinned_msg_id)
                if pinned_msg and pinned_msg.text:
                    pinned_cands = extract_candidates_from_text(pinned_msg.text, channel_username)
                    all_candidates.extend(pinned_cands)
            except Exception:
                pass
    except Exception:
        pass

    # B. Fetch up to 300 recent messages
    try:
        messages_text_list = []
        async for msg in client.iter_messages(entity, limit=300):
            txt = msg.text or msg.message or ""
            if txt:
                messages_text_list.append(txt)
                
            # Check for inline keyboard buttons (e.g. "للتواصل اضغط هنا")
            if msg.reply_markup and isinstance(msg.reply_markup, ReplyInlineMarkup):
                for row in msg.reply_markup.rows:
                    for button in row.buttons:
                        if isinstance(button, KeyboardButtonUrl) and button.url:
                            btn_text = button.text or ""
                            url_cands = extract_candidates_from_text(f"{btn_text} {button.url}", channel_username)
                            all_candidates.extend(url_cands)

        # Extract from combined text of messages
        combined_msgs = "\n".join(messages_text_list)
        msg_cands = extract_candidates_from_text(combined_msgs, channel_username)
        all_candidates.extend(msg_cands)
    except Exception:
        pass

    # C. Validate candidates live with client.get_entity
    # Remove duplicates preserving order
    seen = set()
    unique_cands = []
    for c in all_candidates:
        if c.lower() not in seen:
            seen.add(c.lower())
            unique_cands.append(c)

    for cand in unique_cands:
        try:
            cand_clean = clean_username(cand)
            if len(cand_clean) < 4 or cand_clean.lower() in SKIP_USERNAMES:
                continue
            cand_ent = await client.get_entity(cand_clean)
            if cand_ent and getattr(cand_ent, 'id', None):
                # Found valid user or contact bot
                return cand_clean
        except errors.FloodWaitError as f:
            await asyncio.sleep(min(f.seconds, 10))
        except Exception:
            continue

    return None

async def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT id FROM campaigns WHERE id::text LIKE %s LIMIT 1", (CAMPAIGN_ID_PREFIX + '%',))
    row = cur.fetchone()
    if not row:
        print("Campaign not found!")
        return
    campaign_id = row['id']

    # Get all failed leads with no contact or uncontactable status
    cur.execute("""
        SELECT cl.id as log_id, l.id as lead_id, l.channel_username, l.member_count, l.description
        FROM campaign_logs cl
        JOIN leads l ON l.id = cl.lead_id
        WHERE cl.campaign_id = %s
          AND cl.status IN ('failed', 'FAILED', 'error', 'ERROR')
          AND cl.error_message ILIKE '%%No owner or admin contact%%'
        ORDER BY l.member_count DESC NULLS LAST
    """, (campaign_id,))
    target_leads = cur.fetchall()

    print(f"==================================================")
    print(f"🚀 DEEP MINING CONTACTS FOR {len(target_leads)} CHANNELS")
    print(f"==================================================\n")

    session_path = get_session_path("user_session")
    client = TelegramClient(session_path, 36318125, '5f2ea025376141a257979750c3fc9cf7')
    await client.connect()
    if not await client.is_user_authorized():
        print("Telethon client unauthorized!")
        return

    me = await client.get_me()
    print(f"Logged in as: {me.first_name} (@{me.username})\n")

    mined_count = 0
    total = len(target_leads)

    for i, lead in enumerate(target_leads, 1):
        ch = lead['channel_username']
        members = lead['member_count'] or 0
        if not ch or ch.startswith('private_'):
            continue

        print(f"[{i:3d}/{total}] Scanning @{ch} ({members:,} members)...", end=" ", flush=True)
        
        contact = await mine_channel(client, ch)
        if contact:
            print(f"🎯 FOUND: @{contact}")
            cur.execute("UPDATE leads SET contact_username = %s WHERE id = %s", (contact, lead['lead_id']))
            cur.execute("UPDATE campaign_logs SET status = 'pending', error_message = NULL, sent_at = NULL WHERE id = %s", (lead['log_id'],))
            conn.commit()
            mined_count += 1
        else:
            print("❌ No contact found")

        # Gentle delay to respect API limits
        await asyncio.sleep(1.5)

    print(f"\n==================================================")
    print(f"✅ FINISHED: Successfully mined and verified {mined_count} new contacts!")
    print(f"==================================================")

    # Final breakdown
    cur.execute("""
        SELECT status, COUNT(*) as cnt
        FROM campaign_logs
        WHERE campaign_id = %s
        GROUP BY status
        ORDER BY cnt DESC
    """, (campaign_id,))
    print("\n=== UPDATED CAMPAIGN STATUS ===")
    for r in cur.fetchall():
        print(f"  {r['status']:10s}: {r['cnt']}")

    await client.disconnect()
    conn.close()

if __name__ == "__main__":
    asyncio.run(main())
