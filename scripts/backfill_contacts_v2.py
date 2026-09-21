"""
scripts/backfill_contacts_v2.py — High-Yield Contact Backfill, Forex Reclamation & Reconciliation

Applies the upgraded multi-surface, emoji-aware contact extraction engine across all channels
in PostgreSQL (`leads` table). Immediately extracts contacts from stored descriptions, pinned messages,
and sampled post texts. Reconciles and reclaims previously skipped/failed Forex leads into `pending_review`.
"""

import os
import sys
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Ensure root dir is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.validator.contact_extractor import extract_contacts, _is_bot, JUNK_USERNAMES
from app.outreach.priority_engine import OutreachPriorityEngine
from app.core.db import get_db_connection

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("backfill_contacts")


def backfill_all():
    conn = get_db_connection()
    logger.info("Connected to PostgreSQL for contact backfill and forex leads reclamation.")

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1. Fetch active campaign
            cur.execute("SELECT id FROM campaigns WHERE status = 'active' ORDER BY created_at DESC LIMIT 1;")
            active_camp_row = cur.fetchone()
            active_camp_id = active_camp_row['id'] if active_camp_row else None
            logger.info(f"Active campaign ID: {active_camp_id or 'None'}")

            # 2. Pre-fetch posts for all channels that have posts in channel_posts in one fast query
            logger.info("Pre-fetching recent posts from channel_posts...")
            cur.execute("""
                SELECT channel_username, string_agg(message_text, ' \n ') as posts_text
                FROM (
                    SELECT channel_username, message_text,
                           ROW_NUMBER() OVER (PARTITION BY channel_username ORDER BY timestamp DESC) as rn
                    FROM channel_posts
                    WHERE message_text IS NOT NULL AND LENGTH(message_text) > 10
                ) sub
                WHERE rn <= 15
                GROUP BY channel_username;
            """)
            post_rows = cur.fetchall()
            posts_map = {r['channel_username']: r['posts_text'] for r in post_rows}
            logger.info(f"Pre-fetched posts for {len(posts_map)} channels.")

            # 3. Fetch all leads that have descriptions or posts
            cur.execute("""
                SELECT id, channel_username, description, contact_username, admin_username, whatsapp, website,
                       status, tier, lead_score, commercial_fit_score, outreach_priority, outreach_priority_score,
                       COALESCE(forex_score, forex_intent_score, 0) as forex_score,
                       COALESCE(is_exchange_hub, FALSE) as is_exchange_hub,
                       COALESCE(is_exchange_seed, FALSE) as is_exchange_seed,
                       COALESCE(exchange_affinity_score, 0) as exchange_affinity_score,
                       COALESCE(member_count, 0) as member_count
                FROM leads
                WHERE (description IS NOT NULL AND description != '')
                   OR channel_username IN (SELECT DISTINCT channel_username FROM channel_posts);
            """)
            leads = cur.fetchall()
            logger.info(f"Found {len(leads)} channels with stored descriptions/posts to evaluate.")

            updated_contacts = 0
            reclaimed_leads = 0
            newly_enrolled = 0

            for idx, lead in enumerate(leads, 1):
                lead_id = lead['id']
                ch_user = lead['channel_username']
                desc = lead['description'] or ''
                curr_contact = lead['contact_username']
                curr_admin = lead['admin_username']
                curr_wa = lead['whatsapp']
                curr_web = lead['website']

                posts_text = posts_map.get(ch_user, '')

                # Extract contacts using upgraded multi-surface engine
                extracted = extract_contacts(text=posts_text, description=desc, channel_username=ch_user)
                new_contact = extracted.get('contact_username')
                new_admin = extracted.get('admin_username')
                new_wa = extracted.get('whatsapp')
                new_web = extracted.get('website')

                updates = []
                params = []

                if new_contact and (not curr_contact or curr_contact.lower() != new_contact.lower()):
                    updates.append("contact_username = %s")
                    params.append(new_contact)

                if new_admin and not curr_admin:
                    updates.append("admin_username = %s")
                    params.append(new_admin)

                if new_wa and not curr_wa:
                    updates.append("whatsapp = %s")
                    params.append(new_wa)

                if new_web and not curr_web:
                    updates.append("website = %s")
                    params.append(new_web)

                if updates:
                    params.append(lead_id)
                    update_sql = f"UPDATE leads SET {', '.join(updates)} WHERE id = %s;"
                    cur.execute(update_sql, tuple(params))
                    updated_contacts += 1

                # Evaluate priority tier
                final_contact = (new_contact or curr_contact or '').strip().lstrip('@')
                forex_score = lead.get('forex_score', 0)
                mem_count = lead.get('member_count', 0)
                ex_affinity = lead.get('exchange_affinity_score', 0)
                is_hub = lead.get('is_exchange_hub', False)

                prio_eval = OutreachPriorityEngine.evaluate_priority(
                    title="",
                    description=desc,
                    recent_messages=[posts_text] if posts_text else [],
                    contacts_dict={'contact_username': final_contact, 'source': 'backfill'},
                    forex_relevance_score=forex_score,
                    member_count=mem_count
                )
                assigned_prio = prio_eval.get("priority", "P3")
                assigned_score = prio_eval.get("priority_score", 25)
                assigned_reason = prio_eval.get("priority_reason", "Auto-reconciled via contact backfill")

                # Reclaim previously failed or skipped Forex leads in campaign_logs
                if final_contact and not _is_bot(final_contact) and final_contact.lower() not in JUNK_USERNAMES:
                    if forex_score >= 30 or lead.get('tier') in ('Tier_A', 'Tier_B', 'Tier_C'):
                        cur.execute("""
                            UPDATE campaign_logs
                            SET status = 'pending_review',
                                error_message = NULL,
                                priority = %s,
                                priority_score = %s,
                                priority_reason = %s
                            WHERE lead_id = %s
                              AND status IN ('skipped', 'failed')
                              AND (
                                error_message ILIKE '%%no contact username%%'
                                OR error_message ILIKE '%%no user has%%'
                                OR error_message ILIKE '%%cannot find any entity%%'
                                OR error_message ILIKE '%%skipped: contact username already messaged%%'
                              );
                        """, (assigned_prio, assigned_score, f"Reclaimed Forex Lead: {assigned_reason}", lead_id))
                        if cur.rowcount > 0:
                            reclaimed_leads += cur.rowcount

                        # Auto-enroll into active campaign as pending_review if not enrolled
                        if active_camp_id and lead['status'] != 'rejected':
                            cur.execute("""
                                INSERT INTO campaign_logs (
                                    id, campaign_id, lead_id, status, priority, priority_score,
                                    priority_reason, commercial_fit_score
                                )
                                SELECT gen_random_uuid(), %s, %s, 'pending_review',
                                       %s, %s, %s, COALESCE(%s, 0)
                                WHERE NOT EXISTS (
                                    SELECT 1 FROM campaign_logs cl WHERE cl.campaign_id = %s AND cl.lead_id = %s
                                );
                            """, (
                                active_camp_id, lead_id,
                                assigned_prio, assigned_score,
                                f"Enrolled via Contact Extraction: {assigned_reason}",
                                lead.get('commercial_fit_score', 0),
                                active_camp_id, lead_id
                            ))
                            if cur.rowcount > 0:
                                newly_enrolled += 1

                if idx % 200 == 0 or idx == len(leads):
                    conn.commit()
                    logger.info(f"Progress: {idx}/{len(leads)} | Updated Contacts: {updated_contacts} | Reclaimed: {reclaimed_leads} | Newly Enrolled: {newly_enrolled}")

            conn.commit()
            logger.info("================ BACKFILL & RECLAMATION COMPLETE ================")
            logger.info(f"Total Channels Processed: {len(leads)}")
            logger.info(f"Total Contacts Extracted/Updated: {updated_contacts}")
            logger.info(f"Total Skipped/Failed Forex Leads Reclaimed: {reclaimed_leads}")
            logger.info(f"Total Newly Enrolled for Review: {newly_enrolled}")
            logger.info("================================================================")

    except Exception as e:
        logger.error(f"Error during contact backfill: {e}", exc_info=True)
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    backfill_all()
