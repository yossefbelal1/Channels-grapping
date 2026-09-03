"""
app/discovery/checkpoint.py — Resumable Search State Tracker & Pagination Checkpointer
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class SearchCheckpointManager:
    """
    Persists pagination and offset states for Telegram global message searches,
    post searches, and web crawls to ensure seamless resumption across restarts.
    Backed by Redis for low-latency atomic updates and PostgreSQL for permanent audit.
    """

    def __init__(self, redis_conn, db_conn=None):
        self.redis = redis_conn
        self.db = db_conn

    def _redis_key(self, search_type: str, query_key: str) -> str:
        safe_query = query_key.strip().lower().replace(" ", "_")
        return f"checkpoint:{search_type}:{safe_query}"

    def save_checkpoint(
        self,
        search_type: str,
        query_key: str,
        offset_id: int = 0,
        offset_rate: int = 0,
        offset_date: Optional[datetime] = None,
        page_number: int = 1,
        total_yield: int = 0,
        status: str = "in_progress"
    ) -> None:
        """Saves current search offset state in Redis and PostgreSQL."""
        key = self._redis_key(search_type, query_key)
        date_str = offset_date.isoformat() if offset_date else None
        
        payload = {
            "search_type": search_type,
            "query_key": query_key,
            "offset_id": offset_id,
            "offset_rate": offset_rate,
            "offset_date": date_str,
            "page_number": page_number,
            "total_yield": total_yield,
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        # 1. Store in Redis with 7-day TTL
        try:
            self.redis.set(key, json.dumps(payload), ex=604800)
        except Exception as err:
            logger.warning(f"Failed to cache search checkpoint in Redis: {err}")

        # 2. Store in PostgreSQL if connection provided
        if self.db:
            try:
                with self.db.cursor() as cur:
                    cur.execute("""
                        INSERT INTO discovery_checkpoints (
                            search_type, query_key, last_offset_id, last_offset_rate,
                            last_offset_date, page_number, total_yield, status, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (search_type, query_key) DO UPDATE SET
                            last_offset_id = EXCLUDED.last_offset_id,
                            last_offset_rate = EXCLUDED.last_offset_rate,
                            last_offset_date = EXCLUDED.last_offset_date,
                            page_number = EXCLUDED.page_number,
                            total_yield = EXCLUDED.total_yield,
                            status = EXCLUDED.status,
                            updated_at = NOW();
                    """, (search_type, query_key, offset_id, offset_rate, offset_date, page_number, total_yield, status))
                self.db.commit()
            except Exception as db_err:
                logger.warning(f"Failed to persist search checkpoint in DB: {db_err}")
                try:
                    self.db.rollback()
                except Exception:
                    pass

    def get_checkpoint(self, search_type: str, query_key: str) -> Optional[Dict[str, Any]]:
        """Retrieves active search checkpoint from Redis (fallback to DB)."""
        key = self._redis_key(search_type, query_key)
        try:
            cached = self.redis.get(key)
            if cached:
                return json.loads(cached)
        except Exception as err:
            logger.warning(f"Failed to read search checkpoint from Redis: {err}")

        if self.db:
            try:
                with self.db.cursor() as cur:
                    cur.execute("""
                        SELECT last_offset_id as offset_id, last_offset_rate as offset_rate,
                               last_offset_date as offset_date, page_number, total_yield, status
                        FROM discovery_checkpoints
                        WHERE search_type = %s AND query_key = %s
                    """, (search_type, query_key))
                    row = cur.fetchone()
                    if row:
                        return dict(row)
            except Exception as db_err:
                logger.warning(f"Failed to read search checkpoint from DB: {db_err}")

        return None

    def mark_completed(self, search_type: str, query_key: str, total_yield: int = 0) -> None:
        """Marks a search checkpoint as fully traversed."""
        self.save_checkpoint(
            search_type=search_type,
            query_key=query_key,
            total_yield=total_yield,
            status="completed"
        )

    def mark_rate_limited(self, search_type: str, query_key: str, last_offset_id: int, total_yield: int) -> None:
        """Marks a search checkpoint as paused due to rate limits."""
        self.save_checkpoint(
            search_type=search_type,
            query_key=query_key,
            offset_id=last_offset_id,
            total_yield=total_yield,
            status="rate_limited"
        )
