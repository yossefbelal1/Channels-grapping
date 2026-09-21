"""
scripts/backfill_contacts_v2.py — High-Yield Contact Backfill & Auto-Enrollment

Applies the upgraded multi-surface, emoji-aware contact extraction engine across all existing
channels in PostgreSQL (`leads` table), immediately extracting contacts from stored descriptions,
pinned messages, and post texts, and auto-enrolling newly resolved qualified leads into the active campaign.
"""

import os
import sys
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Ensure root dir is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.validator.contact_extractor import extract_contacts

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("backfill_contacts")


def get_db_connection():
    load_dotenv()
    db_host = os.getenv("POSTGRES_HOST", "localhost")
    db_port = os.getenv("POSTGRES_PORT", "5432")
    db_name = os.getenv("POSTGRES_DB", "leadhunter_db")
    db_user = os.getenv("POSTGRES_USER", "postgres")
    db_pass = os.getenv("POSTGRES_PASSWORD", "leadhunter_pass")

    return psycopg2.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_pass
    )


def backfill_all():
    conn = get_db_connection()
    logger.info("Connected to PostgreSQL for contact backfill.")

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1. Fetch active campaign
            cur.execute("SELECT id FROM campaigns WHERE status = 'active' ORDER BY created_at DESC LIMIT 1;")
            active_camp_row = cur.fetchone()
            active_camp_id = active_camp_row['id'] if active_camp_row else None
            logger.info(f"Active campaign ID: {active_camp_id or 'None (Enrollment will skip)'}")

            # 2. Fetch all leads that have descriptions
            cur.execute("""
                SELECT id, channel_username, description, contact_username, whatsapp, website,
                       status, tier, lead_score, commercial_fit_score, outreach_priority, outreach_priority_score
                FROM leads
                WHERE (description IS NOT NULL AND description != '')
                   OR id IN (SELECT DISTINCT lead_id FROM channel_posts WHERE lead_id IS NOT NULL);
            """)
            leads = cur.fetchall()
            logger.info(f"Found {len(leads)} channels with stored descriptions/posts to evaluate.")

            updated_contacts = 0
            newly_enrolled = 0

            for idx, lead in enumerate(leads, 1):
                lead_id = lead['id']
                ch_user = lead['channel_username']
                desc = lead['description'] or ''
                curr_contact = lead['contact_username']
                curr_wa = lead['whatsapp']
                curr_web = lead['website']

                # Fetch sample posts
                cur.execute("""
                    SELECT message_text
                    FROM channel_posts
                    WHERE channel_username = %s
                    ORDER BY id DESC
                    LIMIT 20;
                """, (ch_user,))
                post_rows = cur.fetchall()
                posts_text = " \n ".join([p['message_text'] for p in post_rows if p.get('message_text')])

                # Extract contacts using upgraded engine
                extracted = extract_contacts(text=posts_text, description=desc, channel_username=ch_user)
                new_contact = extracted.get('contact_username')
                new_wa = extracted.get('whatsapp')
                new_web = extracted.get('website')

                updates = []
                params = []

                if new_contact and (not curr_contact or curr_contact.lower() != new_contact.lower()):
                    updates.append("contact_username = %s")
                    params.append(new_contact)

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

                # Auto-enroll newly resolved qualified leads into active campaign
                final_contact = new_contact or curr_contact
                is_qualified = (lead['status'] == 'new' or lead['tier'] in ('Tier_A', 'Tier_B', 'Tier_C'))
                if active_camp_id and is_qualified and final_contact:
                    cur.execute("""
                        INSERT INTO campaign_logs (id, campaign_id, lead_id, status, priority, priority_score, priority_reason, commercial_fit_score)
                        SELECT gen_random_uuid(), %s, %s, 'approved',
                               COALESCE(%s, 'P2'),
                               COALESCE(%s, 50),
                               'Auto-enrolled via Contact Backfill',
                               COALESCE(%s, 0)
                        WHERE NOT EXISTS (
                            SELECT 1 FROM campaign_logs cl
                            JOIN leads l ON cl.lead_id = l.id
                            WHERE LOWER(l.contact_username) = LOWER(%s)
                        );
                    """, (
                        active_camp_id, lead_id,
                        lead['outreach_priority'], lead['outreach_priority_score'],
                        lead['commercial_fit_score'], final_contact
                    ))
                    if cur.rowcount > 0:
                        newly_enrolled += 1

                if idx % 100 == 0 or idx == len(leads):
                    conn.commit()
                    logger.info(f"Progress: {idx}/{len(leads)} processed | Updated Contacts: {updated_contacts} | Enrolled: {newly_enrolled}")

            conn.commit()
            logger.info("================ BACKFILL COMPLETE ================")
            logger.info(f"Total Processed: {len(leads)}")
            logger.info(f"Total Contacts Updated: {updated_contacts}")
            logger.info(f"Total Newly Enrolled for Outreach: {newly_enrolled}")
            logger.info("====================================================")

    except Exception as e:
        logger.error(f"Error during contact backfill: {e}", exc_info=True)
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    backfill_all()
