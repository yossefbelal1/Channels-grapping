"""
app/scheduler/watermark_manager.py — Incremental Post Watermark Tracking

Tracks last_scanned_message_id per channel in PostgreSQL leads table and Redis cache,
ensuring repeated crawls only scan newly posted messages rather than historical archives.
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class WatermarkManager:
    """
    Manages channel message scan watermarks for incremental scraping.
    """

    def __init__(self, redis_conn=None, db_conn=None):
        self.redis = redis_conn
        self.db = db_conn

    def _redis_key(self, channel_id: str) -> str:
        return f"watermark:channel:{channel_id}"

    def get_watermark(self, channel_id: str, channel_username: Optional[str] = None) -> int:
        """
        Retrieves the last scanned message ID for a channel.
        Checks Redis cache first, falling back to PostgreSQL.
        """
        # 1. Check Redis cache
        if self.redis:
            try:
                cached = self.redis.get(self._redis_key(channel_id))
                if cached is not None:
                    return int(cached)
            except Exception as err:
                logger.debug(f"Redis watermark cache read failed: {err}")

        # 2. Query PostgreSQL
        if self.db:
            try:
                with self.db.cursor() as cur:
                    if channel_username:
                        cur.execute(
                            "SELECT last_scanned_message_id FROM leads WHERE id::text = %s OR channel_username = %s LIMIT 1;",
                            (str(channel_id), channel_username)
                        )
                    else:
                        cur.execute(
                            "SELECT last_scanned_message_id FROM leads WHERE id::text = %s LIMIT 1;",
                            (str(channel_id),)
                        )
                    row = cur.fetchone()
                    if row and row[0] is not None:
                        val = int(row[0])
                        # Populate Redis cache
                        if self.redis:
                            try:
                                self.redis.setex(self._redis_key(channel_id), 86400, val)
                            except Exception:
                                pass
                        return val
            except Exception as err:
                logger.warning(f"Failed to query watermark from DB for channel {channel_id}: {err}")

        return 0

    def update_watermark(
        self,
        channel_id: str,
        new_message_id: Optional[int] = None,
        channel_username: Optional[str] = None,
        new_watermark: Optional[int] = None
    ) -> int:
        """
        Updates the watermark for a channel, ensuring monotonicity (never regresses).
        """
        target_id = new_watermark if new_watermark is not None else (new_message_id or 0)
        if target_id <= 0:
            return 0

        # 1. Update PostgreSQL with GREATEST constraint
        if self.db:
            try:
                with self.db.cursor() as cur:
                    if channel_username:
                        cur.execute("""
                            UPDATE leads
                            SET last_scanned_message_id = GREATEST(COALESCE(last_scanned_message_id, 0), %s),
                                last_crawl_at = NOW(),
                                last_successful_crawl_at = NOW(),
                                consecutive_crawl_failures = 0
                            WHERE id::text = %s OR channel_username = %s;
                        """, (target_id, str(channel_id), channel_username))
                    else:
                        cur.execute("""
                            UPDATE leads
                            SET last_scanned_message_id = GREATEST(COALESCE(last_scanned_message_id, 0), %s),
                                last_crawl_at = NOW(),
                                last_successful_crawl_at = NOW(),
                                consecutive_crawl_failures = 0
                            WHERE id::text = %s;
                        """, (target_id, str(channel_id)))
                self.db.commit()
            except Exception as err:
                logger.warning(f"Failed to update watermark in DB for channel {channel_id}: {err}")
                try:
                    self.db.rollback()
                except Exception:
                    pass

        # 2. Update Redis cache
        if self.redis:
            try:
                key = self._redis_key(channel_id)
                self.redis.setex(key, 86400, target_id)
                if channel_username and channel_username != str(channel_id):
                    self.redis.setex(self._redis_key(channel_username), 86400, target_id)
            except Exception as err:
                logger.debug(f"Failed to update Redis watermark cache: {err}")

        return target_id
