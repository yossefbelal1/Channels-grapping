"""
app/discovery/provenance.py — Candidate Identity, Multi-Source Provenance & Deduplication Manager
"""

import json
import logging
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class ProvenanceManager:
    """
    Manages canonical candidate identity, multi-source provenance tracking,
    and deduplication across all discovery mechanisms.
    """

    def __init__(self, redis_conn, db_conn=None):
        self.redis = redis_conn
        self.db = db_conn

    @staticmethod
    def canonical_username(identifier: str) -> str:
        """
        Normalizes any username, t.me link, or handle into a clean lowercase canonical username.
        Examples:
          '@Forex_Arabic' -> 'forex_arabic'
          'https://t.me/Forex_Arabic' -> 'forex_arabic'
          't.me/joinchat/...' -> 'joinchat/...' (if private)
        """
        if not identifier:
            return ""
        
        clean = identifier.strip()
        if clean.startswith("https://t.me/"):
            clean = clean[13:]
        elif clean.startswith("http://t.me/"):
            clean = clean[12:]
        elif clean.startswith("t.me/"):
            clean = clean[5:]
        elif clean.startswith("@"):
            clean = clean[1:]

        # Strip query parameters if present
        clean = clean.split("?")[0].strip()
        return clean.lower()

    def record_candidate_discovery(
        self,
        username_or_link: str,
        source_type: str,
        keyword: str = "",
        referrer_channel_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, int, List[str]]:
        """
        Records a newly discovered candidate in Redis and tracks multi-source provenance.
        
        Returns:
            Tuple of (is_first_time_seen: bool, total_discovery_count: int, all_sources: List[str])
        """
        canonical = self.canonical_username(username_or_link)
        if not canonical:
            return False, 0, []

        sources_key = f"provenance:sources:{canonical}"
        count_key = f"provenance:count:{canonical}"

        is_new = False
        all_sources = []
        count = 1

        try:
            # Atomic SADD to sources set
            added = self.redis.sadd(sources_key, source_type)
            # Atomic INCR to total discovery counter
            count = self.redis.incr(count_key)
            self.redis.expire(sources_key, 2592000)  # 30 days
            self.redis.expire(count_key, 2592000)

            raw_sources = self.redis.smembers(sources_key)
            all_sources = [s.decode() if isinstance(s, bytes) else str(s) for s in raw_sources]
            is_new = (count == 1)
        except Exception as err:
            logger.warning(f"Redis provenance tracking error: {err}")
            all_sources = [source_type]
            count = 1

        return is_new, count, all_sources

    def persist_provenance_to_db(
        self,
        channel_id: str,
        source_type: str,
        keyword_or_query: str = "",
        referrer_channel_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Persists source record to channel_sources table and updates leads table."""
        if not self.db or not channel_id:
            return

        try:
            meta_json = json.dumps(metadata or {})
            with self.db.cursor() as cur:
                # 1. Insert into channel_sources
                cur.execute("""
                    INSERT INTO channel_sources (
                        channel_id, source_type, keyword_or_query, referrer_channel_id, metadata
                    ) VALUES (%s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (channel_id, source_type, keyword_or_query, referrer_channel_id)
                    DO UPDATE SET metadata = EXCLUDED.metadata;
                """, (channel_id, source_type, keyword_or_query or '', referrer_channel_id, meta_json))

                # 2. Update leads discovery count and sources array
                cur.execute("""
                    UPDATE leads
                    SET discovery_count = COALESCE(discovery_count, 0) + 1,
                        discovered_by = array_append(
                            ARRAY(SELECT DISTINCT unnest(discovered_by)),
                            %s
                        )
                    WHERE id = %s;
                """, (source_type, channel_id))

            self.db.commit()
        except Exception as db_err:
            logger.warning(f"Failed to persist channel provenance in DB: {db_err}")
            try:
                self.db.rollback()
            except Exception:
                pass
