"""
app/graph/graph_importance.py — Lightweight Graph Centrality & Importance Engine (PART J)

Computes a transparent graph importance score (0 to 100) based on:
- In-degree (incoming recommendations, mentions, forwards from other channels)
- Out-degree (breadth of relationships identified)
- Edge diversity (mix of FORWARDED_FROM, RECOMMENDATION, MENTION, LINK)
- Independent discovery sources count
- Recurring edges / high citation weight
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class GraphImportanceCalculator:
    """
    Computes graph importance signals for channels in the discovery network.
    """

    def __init__(self, db_conn=None):
        self.db = db_conn

    @staticmethod
    def calculate_importance_score(
        in_degree: int = 0,
        out_degree: int = 0,
        unique_relation_types: int = 0,
        recommendation_in_count: int = 0,
        forward_in_count: int = 0,
        mention_in_count: int = 0,
        discovery_source_count: int = 1
    ) -> Dict[str, Any]:
        """
        Pure computational formula for graph importance.
        Returns score (0-100) and structured evidence breakdown.
        """
        points = 0

        # 1. In-Degree / Inbound Citations (max 40 pts)
        # Channels referenced by others are critical hub signal providers
        if in_degree >= 20:
            points += 40
        elif in_degree >= 10:
            points += 30
        elif in_degree >= 5:
            points += 20
        elif in_degree >= 2:
            points += 12
        elif in_degree >= 1:
            points += 6

        # 2. Recommendations Received (max 20 pts)
        # Telegram's official similar channel recommendation is an authoritative clustering signal
        if recommendation_in_count >= 5:
            points += 20
        elif recommendation_in_count >= 2:
            points += 15
        elif recommendation_in_count >= 1:
            points += 10

        # 3. Forwards Received (max 15 pts)
        # Being forwarded by other channels proves content syndication & authority
        if forward_in_count >= 10:
            points += 15
        elif forward_in_count >= 3:
            points += 10
        elif forward_in_count >= 1:
            points += 5

        # 4. Edge Diversity (max 15 pts)
        # Multi-edge confirmation (e.g. forward + recommendation + mention)
        if unique_relation_types >= 4:
            points += 15
        elif unique_relation_types >= 2:
            points += 10
        elif unique_relation_types >= 1:
            points += 5

        # 5. Multi-Source Discovery Diversity (max 10 pts)
        # Found across global search, web, search_posts, etc.
        if discovery_source_count >= 3:
            points += 10
        elif discovery_source_count >= 2:
            points += 6
        elif discovery_source_count >= 1:
            points += 2

        score = max(0, min(100, points))

        evidence = {
            "graph_importance_score": score,
            "in_degree": in_degree,
            "out_degree": out_degree,
            "unique_relation_types": unique_relation_types,
            "recommendation_in_count": recommendation_in_count,
            "forward_in_count": forward_in_count,
            "mention_in_count": mention_in_count,
            "discovery_source_count": discovery_source_count
        }

        return {
            "score": score,
            "evidence": evidence
        }

    def compute_and_update_channel(self, channel_id: str) -> int:
        """
        Queries channel_edges and channel_sources for a channel and updates
        graph_importance_score in leads table.
        """
        if not self.db:
            return 0

        try:
            with self.db.cursor() as cur:
                # Inbound edges
                cur.execute("""
                    SELECT relation_type, COUNT(*)
                    FROM channel_edges
                    WHERE target_channel_id = %s
                    GROUP BY relation_type;
                """, (str(channel_id),))
                inbound_rows = cur.fetchall()

                in_degree = sum(r[1] for r in inbound_rows)
                rel_types = set(r[0] for r in inbound_rows)
                recs_in = sum(r[1] for r in inbound_rows if r[0] == 'RECOMMENDATION')
                fwds_in = sum(r[1] for r in inbound_rows if r[0] == 'FORWARDED_FROM')
                mentions_in = sum(r[1] for r in inbound_rows if r[0] == 'MENTION')

                # Outbound edges
                cur.execute("""
                    SELECT COUNT(*) FROM channel_edges WHERE source_channel_id = %s;
                """, (str(channel_id),))
                out_degree = cur.fetchone()[0] or 0

                # Discovery source count
                cur.execute("""
                    SELECT COUNT(DISTINCT source_type) FROM channel_sources WHERE channel_id = %s;
                """, (str(channel_id),))
                src_count = cur.fetchone()[0] or 1

                res = self.calculate_importance_score(
                    in_degree=in_degree,
                    out_degree=out_degree,
                    unique_relation_types=len(rel_types),
                    recommendation_in_count=recs_in,
                    forward_in_count=fwds_in,
                    mention_in_count=mentions_in,
                    discovery_source_count=src_count
                )
                score = res["score"]

                cur.execute("""
                    UPDATE leads
                    SET graph_importance_score = %s
                    WHERE id::text = %s;
                """, (score, str(channel_id)))
            self.db.commit()
            return score
        except Exception as err:
            logger.warning(f"Failed to compute graph importance for {channel_id}: {err}")
            try:
                self.db.rollback()
            except Exception:
                pass
            return 0
