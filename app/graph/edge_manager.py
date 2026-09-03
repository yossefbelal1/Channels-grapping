"""
app/graph/edge_manager.py — Multi-Edge Relationship Engine
"""

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class EdgeRelation:
    MENTION = "mention"                 # @username mention in post text
    FORWARDED_FROM = "forwarded_from"   # Post forwarded from origin channel
    PROMOTED = "promoted"               # Sponsored or ad-exchange promotional post
    LINKED = "linked"                   # Direct t.me URL or invite link in post/button
    RECOMMENDED = "recommended"         # Telegram official similar channel recommendation

    ALL = [MENTION, FORWARDED_FROM, PROMOTED, LINKED, RECOMMENDED]


class GraphEdgeManager:
    """
    Persists and analyzes multi-edge relationships between Telegram channels.
    """

    def __init__(self, db_conn=None, redis_conn=None):
        self.db = db_conn
        self.redis = redis_conn

    def record_edge(
        self,
        source_channel_id: str,
        target_channel_id: str,
        relation_type: str,
        confidence: int = 100,
        evidence: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Records or increments a directed relationship edge in PostgreSQL.
        Automatically increments occurrence_count and updates last_seen.
        """
        if not self.db or not source_channel_id or not target_channel_id:
            return

        if source_channel_id == target_channel_id:
            return  # Ignore self-loops

        meta_json = json.dumps(metadata or {})
        try:
            with self.db.cursor() as cur:
                cur.execute("""
                    INSERT INTO channel_edges (
                        source_channel_id, target_channel_id, relation_type,
                        confidence, evidence, occurrence_count, first_seen, last_seen, metadata
                    ) VALUES (%s, %s, %s, %s, %s, 1, NOW(), NOW(), %s::jsonb)
                    ON CONFLICT (source_channel_id, target_channel_id, relation_type)
                    DO UPDATE SET
                        occurrence_count = channel_edges.occurrence_count + 1,
                        last_seen = NOW(),
                        evidence = CASE WHEN EXCLUDED.evidence != '' THEN EXCLUDED.evidence ELSE channel_edges.evidence END,
                        confidence = LEAST(100, channel_edges.confidence + 5),
                        metadata = channel_edges.metadata || EXCLUDED.metadata;
                """, (source_channel_id, target_channel_id, relation_type, confidence, evidence[:1000], meta_json))

                # Also insert into legacy channel_graph table for backwards compatibility
                cur.execute("""
                    INSERT INTO channel_graph (source_channel_id, target_channel_id, relation_type, created_at)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (source_channel_id, target_channel_id) DO NOTHING;
                """, (source_channel_id, target_channel_id, relation_type))

            self.db.commit()
        except Exception as err:
            logger.warning(f"Failed to record graph edge ({source_channel_id} -> {target_channel_id}): {err}")
            try:
                self.db.rollback()
            except Exception:
                pass

    def get_channel_network(self, channel_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves in-degree and out-degree connected channels for graph exploration."""
        if not self.db:
            return []

        try:
            with self.db.cursor() as cur:
                cur.execute("""
                    SELECT ce.relation_type, ce.confidence, ce.occurrence_count,
                           ce.last_seen, ce.evidence,
                           l_target.channel_username as target_username,
                           l_target.member_count as target_members,
                           l_target.lead_score as target_score
                    FROM channel_edges ce
                    JOIN leads l_target ON ce.target_channel_id = l_target.id
                    WHERE ce.source_channel_id = %s
                    ORDER BY ce.occurrence_count DESC, ce.last_seen DESC
                    LIMIT %s;
                """, (channel_id, limit))
                return [dict(r) for r in cur.fetchall()]
        except Exception as err:
            logger.warning(f"Failed to query channel network: {err}")
            return []
