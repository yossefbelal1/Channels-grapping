"""
app/repositories/campaign_repository.py — Outreach Campaigns Repository
"""

import uuid
from datetime import datetime
from app.core.db import get_db_cursor


class CampaignRepository:
    """Repository for managing campaign messages, logs, and state transitions."""

    @staticmethod
    def get_active_campaign():
        with get_db_cursor() as cur:
            cur.execute("SELECT * FROM campaigns WHERE status = 'active' ORDER BY created_at DESC LIMIT 1")
            return cur.fetchone()

    @staticmethod
    def create_campaign(message_text: str, media_path: str = None, selected_lead_ids: list = None) -> tuple:
        campaign_id = str(uuid.uuid4())
        with get_db_cursor() as cur:
            cur.execute(
                "INSERT INTO campaigns (id, message_text, media_path, status, created_at) VALUES (%s, %s, %s, %s, %s)",
                (campaign_id, message_text, media_path, "active", datetime.now())
            )
            inserted_logs = 0
            if selected_lead_ids:
                for lead_id in selected_lead_ids:
                    log_id = str(uuid.uuid4())
                    cur.execute(
                        "INSERT INTO campaign_logs (id, campaign_id, lead_id, status) VALUES (%s, %s, %s, %s)",
                        (log_id, campaign_id, lead_id, "pending")
                    )
                    inserted_logs += 1
        return campaign_id, inserted_logs

    @staticmethod
    def auto_enqueue_eligible_leads(campaign_id: str) -> int:
        with get_db_cursor() as cur:
            cur.execute("""
                INSERT INTO campaign_logs (id, campaign_id, lead_id, status)
                SELECT gen_random_uuid(), %s, l.id, 'pending'
                FROM leads l
                WHERE l.contact_username IS NOT NULL
                  AND l.contact_username != ''
                  AND LOWER(l.contact_username) NOT IN ('addlist', 'share', 'joinchat', 'setlanguage', 'proxy', 'socks', 'c', 's', 'm', 'i')
                  AND (l.description IS NULL OR (l.description NOT LIKE 'Blacklisted entity%%' AND l.description NOT LIKE 'Entity does not exist%%'))
                  AND l.id NOT IN (SELECT lead_id FROM campaign_logs WHERE campaign_id = %s)
                ON CONFLICT (id) DO NOTHING
            """, (campaign_id, campaign_id))
            return cur.rowcount

    @staticmethod
    def get_campaign_summaries():
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT c.id, c.created_at, c.message_text, c.media_path, c.status,
                       c.followup_enabled, c.followup_message_text, c.followup_delay_days,
                       COUNT(cl.id) as total_recipients,
                       COUNT(CASE WHEN cl.status = 'sent' THEN 1 END) as sent_count,
                       COUNT(CASE WHEN cl.status = 'failed' THEN 1 END) as failed_count,
                       COUNT(CASE WHEN cl.status = 'skipped' THEN 1 END) as skipped_count,
                       COUNT(CASE WHEN cl.status = 'pending' THEN 1 END) as pending_count,
                       COUNT(CASE WHEN cl.followup_status = 'sent' THEN 1 END) as followup_sent_count,
                       COUNT(CASE WHEN cl.user_replied = TRUE THEN 1 END) as replied_count,
                       COUNT(CASE WHEN cl.status = 'sent' AND (cl.followup_status IS NULL OR cl.followup_status = 'pending') AND cl.user_replied = FALSE AND cl.sent_at < NOW() - (COALESCE(c.followup_delay_days, 4) || ' days')::INTERVAL THEN 1 END) as followup_ready_count
                FROM campaigns c
                LEFT JOIN campaign_logs cl ON c.id = cl.campaign_id
                GROUP BY c.id, c.created_at, c.message_text, c.media_path, c.status, c.followup_enabled, c.followup_message_text, c.followup_delay_days
                ORDER BY c.created_at DESC
            """)
            campaigns = cur.fetchall()

            cur.execute("""
                SELECT cl.campaign_id, cl.status, cl.error_message, cl.sent_at,
                       l.channel_username, l.contact_username, c.message_text
                FROM campaign_logs cl
                JOIN campaigns c ON cl.campaign_id = c.id
                JOIN leads l ON cl.lead_id = l.id
                ORDER BY cl.sent_at DESC NULLS FIRST, c.created_at DESC
                LIMIT 50
            """)
            logs = cur.fetchall()

            return campaigns, logs
