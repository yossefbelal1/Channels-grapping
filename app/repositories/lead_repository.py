"""
app/repositories/lead_repository.py — Lead & Channel Persistence Repository
"""

import logging
from datetime import datetime
from app.core.db import get_db_cursor


class LeadRepository:
    """Repository for querying, inserting, and updating Telegram channel leads."""

    @staticmethod
    def get_by_username(username: str):
        username = username.strip().lstrip('@').lower()
        with get_db_cursor() as cur:
            cur.execute("SELECT * FROM leads WHERE LOWER(channel_username) = %s LIMIT 1", (username,))
            return cur.fetchone()

    @staticmethod
    def get_by_id(lead_id: str):
        with get_db_cursor() as cur:
            cur.execute("SELECT * FROM leads WHERE id = %s LIMIT 1", (lead_id,))
            return cur.fetchone()

    @staticmethod
    def is_blacklisted(entity_or_link: str) -> bool:
        clean = entity_or_link.strip().lstrip('@').lower()
        with get_db_cursor() as cur:
            cur.execute("SELECT 1 FROM blacklist WHERE LOWER(entity_username_or_link) = %s LIMIT 1", (clean,))
            return bool(cur.fetchone())

    @staticmethod
    def update_lead_status(lead_id: str, status: str):
        with get_db_cursor() as cur:
            cur.execute(
                "UPDATE leads SET status = %s, last_activity = %s WHERE id = %s",
                (status, datetime.now(), lead_id)
            )

    @staticmethod
    def update_last_graph_scan(channel_username: str):
        username = channel_username.strip().lstrip('@')
        with get_db_cursor() as cur:
            cur.execute(
                "UPDATE leads SET last_graph_scan = NOW() WHERE LOWER(channel_username) = LOWER(%s)",
                (username,)
            )
