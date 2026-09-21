"""
app/graph/exchange_graph_engine.py — Active Graph Mining, Cluster Detection & Multi-Hop Expansion

Transforms the database graph (channel_edges, channel_graph) into an active discovery mechanism:
1. Multi-Hop Expansion (A -> B -> C -> D)
2. Exchange Hubs Detection (nodes with multiple cross-promotions)
3. Cross-Promotion Clusters & Reciprocal Edges (A <-> B)
4. Automated Harvest of high-potential exchange candidate leads
"""

import json
import logging
from typing import Dict, Any, List, Optional, Set, Tuple
from datetime import datetime

logger = logging.getLogger("exchange_graph_engine")

PROMO_RELATIONS = (
    'promoted', 'advertisement', 'forwarded_from', 'recommendation',
    'mention', 'graph_mention', 'link', 'graph_link'
)


class ExchangeGraphEngine:
    """
    Graph mining engine that detects exchange hubs, promotion clusters,
    and performs multi-hop candidate discovery.
    """

    def __init__(self, db_conn=None):
        self.db = db_conn

    def detect_and_tag_exchange_hubs(self, min_degree: int = 3) -> List[Dict[str, Any]]:
        """
        Scans channel_edges for channels acting as promotion or recommendation hubs
        and tags them with is_exchange_hub = TRUE in the leads table.
        """
        if not self.db:
            return []

        hubs: List[Dict[str, Any]] = []
        try:
            with self.db.cursor() as cur:
                # Find channels with high outbound promotion activity
                cur.execute("""
                    SELECT ce.source_channel_id as channel_id,
                           l.channel_username,
                           l.title,
                           l.member_count,
                           l.forex_intent_score,
                           COUNT(DISTINCT ce.target_channel_id) as distinct_targets,
                           COUNT(*) as total_edges,
                           ARRAY_AGG(DISTINCT ce.relation_type) as rel_types
                    FROM channel_edges ce
                    JOIN leads l ON ce.source_channel_id = l.id
                    WHERE ce.relation_type = ANY(%s)
                      AND l.status != 'rejected'
                    GROUP BY ce.source_channel_id, l.channel_username, l.title, l.member_count, l.forex_intent_score
                    HAVING COUNT(DISTINCT ce.target_channel_id) >= %s
                    ORDER BY distinct_targets DESC
                    LIMIT 100;
                """, (list(PROMO_RELATIONS), min_degree))
                rows = cur.fetchall() or []

                for r in rows:
                    cid = str(r["channel_id"] if isinstance(r, dict) else r[0])
                    uname = (r["channel_username"] if isinstance(r, dict) else r[1]) or ""
                    title = (r["title"] if isinstance(r, dict) else r[2]) or ""
                    mcount = (r["member_count"] if isinstance(r, dict) else r[3]) or 0
                    fscore = (r["forex_intent_score"] if isinstance(r, dict) else r[4]) or 0
                    dtarg = (r["distinct_targets"] if isinstance(r, dict) else r[5]) or 0
                    tedges = (r["total_edges"] if isinstance(r, dict) else r[6]) or 0
                    rels = (r["rel_types"] if isinstance(r, dict) else r[7]) or []

                    hub_data = {
                        "channel_id": cid,
                        "channel_username": uname,
                        "title": title,
                        "member_count": mcount,
                        "forex_intent_score": fscore,
                        "distinct_targets": dtarg,
                        "total_edges": tedges,
                        "relation_types": list(rels)
                    }
                    hubs.append(hub_data)

                # Batch update is_exchange_hub flag in leads table
                if hubs:
                    hub_ids = [h["channel_id"] for h in hubs]
                    cur.execute("""
                        UPDATE leads
                        SET is_exchange_hub = TRUE
                        WHERE id = ANY(%s::uuid[]);
                    """, (hub_ids,))
                    if hasattr(self.db, "commit"):
                        self.db.commit()
                    logger.info(f"Tagged {len(hub_ids)} channels as active Exchange Hubs.")

            return hubs
        except Exception as e:
            logger.error(f"Error detecting exchange hubs: {e}")
            return []

    def detect_cross_promotion_clusters(self) -> Dict[str, Any]:
        """
        Detects reciprocal edges (A -> B and B -> A) and groups channels into clusters.
        """
        if not self.db:
            return {"clusters_count": 0, "mutual_pairs": []}

        mutual_pairs: List[Tuple[str, str]] = []
        try:
            with self.db.cursor() as cur:
                # Find reciprocal edges
                cur.execute("""
                    SELECT DISTINCT
                        l1.channel_username as chan_a,
                        l2.channel_username as chan_b,
                        l1.id as id_a,
                        l2.id as id_b
                    FROM channel_edges e1
                    JOIN channel_edges e2 
                      ON e1.source_channel_id = e2.target_channel_id 
                     AND e1.target_channel_id = e2.source_channel_id
                    JOIN leads l1 ON e1.source_channel_id = l1.id
                    JOIN leads l2 ON e1.target_channel_id = l2.id
                    WHERE e1.source_channel_id < e1.target_channel_id
                    LIMIT 200;
                """)
                rows = cur.fetchall() or []
                cluster_counter = 1
                for r in rows:
                    ca = r["chan_a"] if isinstance(r, dict) else r[0]
                    cb = r["chan_b"] if isinstance(r, dict) else r[1]
                    ida = str(r["id_a"] if isinstance(r, dict) else r[2])
                    idb = str(r["id_b"] if isinstance(r, dict) else r[3])
                    mutual_pairs.append((ca, cb))

                    # Assign cluster_id to mutual pairs
                    cid = f"cluster_mutual_{cluster_counter:03d}"
                    cur.execute("""
                        UPDATE leads
                        SET cluster_id = %s
                        WHERE id IN (%s::uuid, %s::uuid) AND cluster_id IS NULL;
                    """, (cid, ida, idb))
                    cluster_counter += 1

                if hasattr(self.db, "commit"):
                    self.db.commit()

            return {
                "clusters_count": len(mutual_pairs),
                "mutual_pairs": mutual_pairs[:50]
            }
        except Exception as e:
            logger.error(f"Error detecting cross-promotion clusters: {e}")
            return {"clusters_count": 0, "mutual_pairs": []}

    def expand_multi_hop_chain(
        self,
        seed_channel_id: str,
        max_hops: int = 3,
        limit_per_hop: int = 15
    ) -> List[Dict[str, Any]]:
        """
        Traverses outbound edges across multiple hops:
        Seed (Hop 0) -> Hop 1 -> Hop 2 -> Hop 3
        Tracks provenance path, decaying confidence, and finds leaf candidates.
        """
        if not self.db or not seed_channel_id:
            return []

        visited_ids: Set[str] = {seed_channel_id}
        current_layer: List[Dict[str, Any]] = [
            {"channel_id": seed_channel_id, "path": [seed_channel_id], "confidence": 100}
        ]
        all_discovered: List[Dict[str, Any]] = []

        try:
            with self.db.cursor() as cur:
                for hop in range(1, max_hops + 1):
                    next_layer: List[Dict[str, Any]] = []
                    layer_ids = [node["channel_id"] for node in current_layer]
                    if not layer_ids:
                        break

                    confidence_multiplier = 0.85 ** hop

                    cur.execute("""
                        SELECT ce.source_channel_id,
                               ce.target_channel_id,
                               ce.relation_type,
                               l.channel_username,
                               l.title,
                               l.member_count,
                               l.forex_intent_score,
                               l.contact_username
                        FROM channel_edges ce
                        JOIN leads l ON ce.target_channel_id = l.id
                        WHERE ce.source_channel_id = ANY(%s::uuid[])
                          AND ce.target_channel_id != ALL(%s::uuid[])
                          AND l.status != 'rejected'
                        LIMIT %s;
                    """, (layer_ids, list(visited_ids), limit_per_hop * len(layer_ids)))
                    edge_rows = cur.fetchall() or []

                    for er in edge_rows:
                        src_id = str(er["source_channel_id"] if isinstance(er, dict) else er[0])
                        tgt_id = str(er["target_channel_id"] if isinstance(er, dict) else er[1])
                        rel = (er["relation_type"] if isinstance(er, dict) else er[2]) or ""
                        uname = (er["channel_username"] if isinstance(er, dict) else er[3]) or ""
                        title = (er["title"] if isinstance(er, dict) else er[4]) or ""
                        mcount = (er["member_count"] if isinstance(er, dict) else er[5]) or 0
                        fscore = (er["forex_intent_score"] if isinstance(er, dict) else er[6]) or 0
                        cuser = (er["contact_username"] if isinstance(er, dict) else er[7]) or ""

                        if tgt_id in visited_ids:
                            continue

                        visited_ids.add(tgt_id)

                        # Find parent path
                        parent_node = next((n for n in current_layer if n["channel_id"] == src_id), None)
                        parent_path = parent_node["path"] if parent_node else [src_id]
                        new_path = parent_path + [tgt_id]

                        node_data = {
                            "channel_id": tgt_id,
                            "channel_username": uname,
                            "title": title,
                            "member_count": mcount,
                            "forex_intent_score": fscore,
                            "contact_username": cuser,
                            "hop": hop,
                            "path": new_path,
                            "provenance": " -> ".join(new_path),
                            "confidence": int(100 * confidence_multiplier),
                            "discovered_via_relation": rel
                        }
                        next_layer.append(node_data)
                        all_discovered.append(node_data)

                    current_layer = next_layer

            return all_discovered
        except Exception as e:
            logger.error(f"Error expanding multi-hop chain: {e}")
            return []

    def harvest_unvalidated_graph_targets(self, limit: int = 200) -> int:
        """
        Discovers targets in channel_edges that were logged during forward/mention scraping
        and ensures they are entered into seed_channels intake and leads table for validation.
        """
        if not self.db:
            return 0

        inserted = 0
        try:
            with self.db.cursor() as cur:
                # Find target channels with high in-degree that are not yet validated
                cur.execute("""
                    SELECT l.channel_username, COUNT(*) as inbound_count
                    FROM channel_edges ce
                    JOIN leads l ON ce.target_channel_id = l.id
                    WHERE l.status = 'new'
                      AND (l.last_scan IS NULL OR l.last_scan < NOW() - INTERVAL '7 days')
                      AND l.channel_username IS NOT NULL
                      AND l.channel_username != ''
                    GROUP BY l.channel_username
                    ORDER BY inbound_count DESC
                    LIMIT %s;
                """, (limit,))
                candidates = cur.fetchall() or []

                for c in candidates:
                    uname = (c["channel_username"] if isinstance(c, dict) else c[0]).lower().strip().lstrip('@')
                    if uname:
                        cur.execute("""
                            INSERT INTO seed_channels (channel_username, source, notes, created_at)
                            VALUES (%s, 'graph_exchange_expansion', 'Discovered via inbound promotion edges', NOW())
                            ON CONFLICT (channel_username) DO NOTHING;
                        """, (uname,))
                        inserted += 1

                if hasattr(self.db, "commit"):
                    self.db.commit()
            logger.info(f"Harvested {inserted} unvalidated high-degree channels from graph into seed_channels.")
            return inserted
        except Exception as e:
            logger.error(f"Error harvesting graph targets: {e}")
            return 0
