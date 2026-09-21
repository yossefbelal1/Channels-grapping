"""
scripts/scan_and_enrich_24h_channels.py — Deep Channel Inspection & Contact Extraction

1. Prunes non-channel junk (names with spaces/dots/Arabic/emojis) from leads table.
2. Identifies and reclassifies user profiles as `user_account`, linking them as contacts to their source channels (e.g. ksa_trader11 -> ABOSALEM2003).
3. Deeply inspects pending 24h channels: fetches titles, descriptions, member counts, recent messages.
4. Uses the upgraded contact extractor to extract owner, admin, analyst, and support contacts.
5. Scores Forex/Gold channels, computes tiers, and auto-enrolls qualified leads with direct contacts into the active campaign.
"""

import os
import sys
import re
import html
import logging
import urllib.request
from typing import Dict, Any, Optional, Tuple, List
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import get_db_connection
from app.validator.contact_extractor import extract_contacts

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("deep_scan_24h")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9,ar;q=0.8'
}

FOREX_KEYWORDS = [
    'forex', 'signals', 'xauusd', 'gold', 'ذهب', 'توصيات', 'تداول', 'عملات',
    'فوركس', 'smc', 'ict', 'منزل التحليل', 'الصفقة', 'الربح', 'الخسارة', 'تحدي',
    'تمويل', 'إشارات', 'مضاربة', 'النفط', 'مؤشرات', 'ناسداك', 'داوجونز', 'us30',
    'nas100', 'crypto', 'بيتكوين', 'التحليل الفني', 'سوق المال', 'استثمار'
]

SPAM_KEYWORDS = [
    'دعم قنوات', 'تبادل نشر', 'زيادة متابعين', 'زيادة أعضاء', 'زيادة اعضاء',
    'تبادل قنوات', 'تبادل اشتراكات', 'ترويج قنوات', 'اضافة اعضاء', 'اعضاء مجانا',
    'fortnite', 'pubg', 'robux', 'nitro', 'giftcard', 'steam key', 'valorant',
    'free fire', 'شحن العاب', 'حسابات نتفليكس', 'اشتراكات نتفلكس', 'iptv'
]


def inspect_channel_web(username: str) -> Optional[Dict[str, Any]]:
    """
    Fetches public web preview for a channel (t.me/s/{username}).
    Returns None if it is a user profile, deleted, or inaccessible.
    """
    clean_user = username.strip().lstrip('@')
    url = f"https://t.me/s/{clean_user}"
    
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            content = resp.read().decode('utf-8', errors='replace')
            
            # Check if it is a real broadcast channel (t.me/s/ contains tgme_channel_info)
            if 'tgme_channel_info' not in content:
                # If tgme_page_extra exists with 'Send Message', it's a personal user account!
                if 'tgme_action_button_new' in content or 'tgme_page_extra' in content:
                    return {"is_channel": False, "is_user": True}
                return None

            # 1. Title
            title_match = re.search(r'<div class="tgme_channel_info_title"[^>]*><span[^>]*>(.*?)</span></div>', content, re.DOTALL)
            if not title_match:
                title_match = re.search(r'<div class="tgme_page_title"[^>]*><span[^>]*>(.*?)</span></div>', content, re.DOTALL)
            raw_title = title_match.group(1) if title_match else clean_user
            title = html.unescape(re.sub(r'<[^>]+>', '', raw_title)).strip()

            # 2. Member / Subscriber Count
            sub_match = re.search(r'<div class="tgme_channel_info_counter"><span class="counter_value">([^<]+)</span>\s*<span class="counter_type">([^<]+)</span>', content)
            members = 0
            if sub_match:
                val_str = sub_match.group(1).replace(' ', '').replace(',', '')
                try:
                    if 'K' in val_str or 'k' in val_str:
                        members = int(float(val_str.lower().replace('k', '')) * 1000)
                    elif 'M' in val_str or 'm' in val_str:
                        members = int(float(val_str.lower().replace('m', '')) * 1000000)
                    else:
                        members = int(val_str)
                except Exception:
                    members = 0

            # 3. Description
            desc_match = re.search(r'<div class="tgme_channel_info_description"[^>]*>(.*?)</div>', content, re.DOTALL)
            raw_desc = desc_match.group(1) if desc_match else ''
            # Replace <br/> with newline
            clean_desc = re.sub(r'<br\s*/?>', '\n', raw_desc)
            clean_desc = html.unescape(re.sub(r'<[^>]+>', '', clean_desc)).strip()

            # 4. Recent Messages
            messages = []
            for msg_block in re.findall(r'<div class="tgme_widget_message_text[^>]*>(.*?)</div>', content, re.DOTALL):
                m_text = re.sub(r'<br\s*/?>', '\n', msg_block)
                m_text = html.unescape(re.sub(r'<[^>]+>', '', m_text)).strip()
                if m_text:
                    messages.append(m_text)

            return {
                "is_channel": True,
                "is_user": False,
                "title": title,
                "members": members,
                "description": clean_desc,
                "messages": messages
            }

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        return None
    except Exception as e:
        logger.debug(f"Web check failed for @{clean_user}: {e}")
        return None


def calculate_forex_score(title: str, description: str, messages: List[str]) -> Tuple[int, str]:
    """Scores Forex intent based on content."""
    combined = f"{title}\n{description}\n" + "\n".join(messages[:15])
    text_lower = combined.lower()

    # Check hard spam
    spam_hits = sum(1 for kw in SPAM_KEYWORDS if kw in text_lower)
    if spam_hits >= 2:
        return 0, 'rejected'

    forex_hits = sum(1 for kw in FOREX_KEYWORDS if kw in text_lower)
    
    score = min(100, forex_hits * 15)
    if any(k in text_lower for k in ['xauusd', 'ذهب', 'forex', 'فوركس', 'توصيات']):
        score = max(score, 60)

    tier = 'Tier_D'
    if score >= 80:
        tier = 'Tier_A'
    elif score >= 50:
        tier = 'Tier_B'
    elif score >= 25:
        tier = 'Tier_C'

    return score, tier


def run_scan():
    conn = get_db_connection()
    logger.info("Connected to PostgreSQL for Deep 24h Channel Scan.")

    try:
        with conn.cursor() as cur:
            # ─────────────────────────────────────────────────────────────────
            # STEP 1: Prune non-username junk rows
            # ─────────────────────────────────────────────────────────────────
            cur.execute("""
                DELETE FROM leads 
                WHERE channel_username ~ '[^a-zA-Z0-9_]'
                   OR length(channel_username) < 4;
            """)
            pruned_count = cur.rowcount
            logger.info(f"Step 1: Pruned {pruned_count} non-username junk records from leads table.")

            # ─────────────────────────────────────────────────────────────────
            # STEP 2: Handle known user accounts (e.g. ksa_trader11 -> ABOSALEM2003)
            # ─────────────────────────────────────────────────────────────────
            cur.execute("""
                UPDATE leads 
                SET status = 'rejected', outreach_priority_reason = 'user_account'
                WHERE channel_username = 'ksa_trader11';
                
                UPDATE leads
                SET contact_username = 'ksa_trader11',
                    admin_username = COALESCE(NULLIF(admin_username, ''), 'ABOSALEM124')
                WHERE channel_username = 'ABOSALEM2003';
            """)
            logger.info("Step 2: Reclassified @ksa_trader11 as user_account and linked as contact to @ABOSALEM2003.")

            # ─────────────────────────────────────────────────────────────────
            # STEP 3: Fetch active campaign ID
            # ─────────────────────────────────────────────────────────────────
            cur.execute("SELECT id FROM campaigns WHERE status = 'active' ORDER BY created_at DESC LIMIT 1;")
            active_camp_row = cur.fetchone()
            active_camp_id = active_camp_row['id'] if active_camp_row else None
            logger.info(f"Active campaign ID: {active_camp_id or 'None'}")

            # ─────────────────────────────────────────────────────────────────
            # STEP 4: Fetch pending 24h channels
            # ─────────────────────────────────────────────────────────────────
            cur.execute("""
                SELECT id, channel_username, description, contact_username, discovery_source
                FROM leads
                WHERE discovered_at >= NOW() - INTERVAL '24 HOURS'
                  AND channel_username ~ '^[a-zA-Z0-9_]{4,32}$'
                  AND status = 'new'
                  AND (lead_score IS NULL OR description IS NULL OR description = '')
                ORDER BY discovered_at DESC
                LIMIT 300;
            """)
            candidates = cur.fetchall()
            logger.info(f"Step 4: Found {len(candidates)} pending 24h channel candidates to deeply inspect.")

            verified_channels = 0
            user_accounts_found = 0
            contacts_extracted = 0
            newly_enrolled = 0

            for idx, cand in enumerate(candidates, 1):
                ch_id = cand['id']
                username = cand['channel_username']
                src = cand['discovery_source']

                info = inspect_channel_web(username)

                if not info:
                    # Inaccessible or dead
                    cur.execute("UPDATE leads SET status = 'rejected', last_scan = NOW() WHERE id = %s;", (ch_id,))
                    continue

                if info.get('is_user'):
                    # It's a personal user account, not a channel!
                    cur.execute("UPDATE leads SET status = 'rejected', outreach_priority_reason = 'user_account', last_scan = NOW() WHERE id = %s;", (ch_id,))
                    user_accounts_found += 1
                    
                    # Link to source channel if available
                    if src and src != 'unknown':
                        clean_src = src.strip().lstrip('@')
                        cur.execute("""
                            UPDATE leads 
                            SET contact_username = COALESCE(NULLIF(contact_username, ''), %s),
                                admin_username = COALESCE(NULLIF(admin_username, ''), %s)
                            WHERE channel_username = %s;
                        """, (username, username, clean_src))
                    continue

                # It is a REAL broadcast channel!
                title = info['title']
                members = info['members']
                desc = info['description']
                messages = info['messages']

                # Extract contacts using all keywords (support, admin, analyst, etc.)
                all_text = "\n".join(messages)
                contacts = extract_contacts(text=all_text, description=desc, channel_username=username)
                contact_user = contacts.get('contact_username')
                owner_user = contacts.get('owner_username')
                admin_user = contacts.get('admin_username')
                wa = contacts.get('whatsapp')
                web = contacts.get('website')

                if contact_user or wa:
                    contacts_extracted += 1

                # Calculate Forex score
                fx_score, tier = calculate_forex_score(title, desc, messages)

                status = 'new' if fx_score >= 20 else 'rejected'

                # Update leads record
                cur.execute("""
                    UPDATE leads 
                    SET title = %s,
                        member_count = %s,
                        description = %s,
                        lead_score = %s,
                        forex_intent_score = %s,
                        tier = %s::tier_level,
                        status = %s,
                        contact_username = %s,
                        owner_username = %s,
                        admin_username = %s,
                        whatsapp = %s,
                        website = %s,
                        last_scan = NOW()
                    WHERE id = %s;
                """, (
                    title, members, desc, fx_score, fx_score, tier, status,
                    contact_user, owner_user, admin_user, wa, web, ch_id
                ))

                if status == 'new':
                    verified_channels += 1

                # Auto-enroll if qualified Forex with contact
                if active_camp_id and status == 'new' and contact_user:
                    cur.execute("""
                        INSERT INTO campaign_logs (id, campaign_id, lead_id, status, priority, priority_score, priority_reason, commercial_fit_score)
                        SELECT gen_random_uuid(), %s, %s, 'approved', 'P2', 60, 'Deep 24h Scan Verified Lead', %s
                        WHERE NOT EXISTS (
                            SELECT 1 FROM campaign_logs cl
                            JOIN leads l ON cl.lead_id = l.id
                            WHERE LOWER(l.contact_username) = LOWER(%s)
                        );
                    """, (active_camp_id, ch_id, fx_score, contact_user))
                    if cur.rowcount > 0:
                        newly_enrolled += 1

                if idx % 25 == 0 or idx == len(candidates):
                    conn.commit()
                    logger.info(f"Progress: {idx}/{len(candidates)} | Verified: {verified_channels} | Users Reclassified: {user_accounts_found} | Contacts: {contacts_extracted} | Enrolled: {newly_enrolled}")

            conn.commit()
            logger.info("================ SCAN AND ENRICH COMPLETE ================")
            logger.info(f"Pruned Junk: {pruned_count}")
            logger.info(f"Candidates Inspected: {len(candidates)}")
            logger.info(f"Real Forex Channels Verified: {verified_channels}")
            logger.info(f"User Accounts Discovered & Linked: {user_accounts_found}")
            logger.info(f"Direct Contacts Extracted: {contacts_extracted}")
            logger.info(f"Newly Auto-Enrolled into Campaign: {newly_enrolled}")
            logger.info("==========================================================")

    except Exception as e:
        logger.error(f"Error during scan and enrich: {e}", exc_info=True)
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    run_scan()
