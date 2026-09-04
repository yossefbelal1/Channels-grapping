"""
app/graph/cross_platform_graph.py — Multi-Platform Cross-Graph Relationship Engine

Extends the core graph architecture to track and traverse directed edges across
Telegram, TikTok, Facebook, and Web entities, preserving full provenance and evidence.
"""

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from app.discovery.entity_model import (
    Platform, EntityType, RelationType, CanonicalIdentity,
    DiscoveredEntity, DiscoveredRelationship
)
from app.graph.edge_manager import GraphEdgeManager, EdgeRelation

logger = logging.getLogger(__name__)


class CrossPlatformGraphManager(GraphEdgeManager):
    """
    Manages cross-platform nodes and multi-edge relationships in PostgreSQL channel_edges.
    """

    def ensure_entity_lead(self, entity: DiscoveredEntity) -> Optional[str]:
        """
        Ensures a discovered entity exists in the leads table and returns its UUID.
        Handles Telegram, TikTok, Facebook, and Web entities seamlessly.
        """
        if not self.db or not entity.canonical_id:
            return None

        # Format channel_username consistently to satisfy UNIQUE(channel_username)
        if entity.platform == Platform.TELEGRAM:
            username_field = entity.username or entity.canonical_id.replace("telegram:", "")
        else:
            username_field = entity.canonical_id

        meta_json = json.dumps(entity.metadata or {})

        try:
            with self.db.cursor() as cur:
                # 1. Check if entity exists by canonical_id or channel_username
                cur.execute("""
                    SELECT id FROM leads 
                    WHERE (canonical_id = %s) 
                       OR (channel_username = %s AND platform = %s)
                    LIMIT 1;
                """, (entity.canonical_id, username_field, entity.platform))
                row = cur.fetchone()
                if row:
                    lead_id = str(row[0] if isinstance(row, (tuple, list)) else row["id"])
                    # Update metadata and url if newly discovered
                    cur.execute("""
                        UPDATE leads 
                        SET url = COALESCE(leads.url, %s),
                            metadata = leads.metadata || %s::jsonb,
                            last_activity = NOW()
                        WHERE id = %s;
                    """, (entity.url, meta_json, lead_id))
                    self.db.commit()
                    return lead_id

                # 2. Insert new lead
                is_rel = entity.metadata.get("is_relevant", True if entity.platform == Platform.TELEGRAM else False)
                cand_status = "verified" if is_rel else "rejected"
                lead_status = "new" if entity.platform == Platform.TELEGRAM else ("verified" if is_rel else "rejected")
                rel_score = int(entity.metadata.get("relevance_score") or (75 if entity.platform == Platform.TELEGRAM else 0))

                cur.execute("""
                    INSERT INTO leads (
                        id, channel_username, platform, entity_type, canonical_id,
                        url, description, status, candidate_status, relevance_score,
                        verified_at, discovered_at, discovery_source,
                        discovery_method, depth, metadata
                    ) VALUES (
                        gen_random_uuid(), %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        NOW(), NOW(), %s,
                        'cross_platform_discovery', %s, %s::jsonb
                    )
                    ON CONFLICT (channel_username) DO UPDATE SET
                        canonical_id = EXCLUDED.canonical_id,
                        platform = EXCLUDED.platform,
                        candidate_status = EXCLUDED.candidate_status,
                        relevance_score = EXCLUDED.relevance_score,
                        url = COALESCE(leads.url, EXCLUDED.url)
                    RETURNING id;
                """, (
                    username_field, entity.platform, entity.entity_type, entity.canonical_id,
                    entity.url, entity.description or "", lead_status, cand_status, rel_score,
                    entity.metadata.get("source", "cross_platform"),
                    entity.depth, meta_json
                ))
                inserted = cur.fetchone()
                lead_id = str(inserted[0] if isinstance(inserted, (tuple, list)) else inserted["id"])
                self.db.commit()
                return lead_id
        except Exception as err:
            logger.warning(f"Error ensuring lead for {entity.canonical_id}: {err}")
            try:
                self.db.rollback()
            except Exception:
                pass
            return None

    def record_cross_platform_edge(
        self,
        relationship: DiscoveredRelationship,
        source_entity: Optional[DiscoveredEntity] = None,
        target_entity: Optional[DiscoveredEntity] = None
    ) -> bool:
        """
        Persists a cross-platform directed edge in channel_edges with complete metadata.
        """
        if not self.db or not relationship.source_canonical_id or not relationship.target_canonical_id:
            return False

        if relationship.source_canonical_id == relationship.target_canonical_id:
            return False

        # Ensure source lead exists
        if not source_entity:
            source_entity = DiscoveredEntity(
                platform=relationship.source_platform,
                entity_type=EntityType.CHANNEL if relationship.source_platform == Platform.TELEGRAM else EntityType.ACCOUNT,
                canonical_id=relationship.source_canonical_id,
                username=relationship.source_canonical_id.split(":", 1)[1] if ":" in relationship.source_canonical_id else relationship.source_canonical_id
            )
        source_lead_id = self.ensure_entity_lead(source_entity)

        # Ensure target lead exists
        if not target_entity:
            target_entity = DiscoveredEntity(
                platform=relationship.target_platform,
                entity_type=EntityType.CHANNEL if relationship.target_platform == Platform.TELEGRAM else EntityType.ACCOUNT,
                canonical_id=relationship.target_canonical_id,
                username=relationship.target_canonical_id.split(":", 1)[1] if ":" in relationship.target_canonical_id else relationship.target_canonical_id
            )
        target_lead_id = self.ensure_entity_lead(target_entity)

        if not source_lead_id or not target_lead_id or source_lead_id == target_lead_id:
            return False

        meta_json = json.dumps(relationship.metadata or {})

        try:
            with self.db.cursor() as cur:
                cur.execute("""
                    INSERT INTO channel_edges (
                        source_channel_id, target_channel_id, relation_type,
                        source_platform, target_platform,
                        confidence, evidence, occurrence_count, first_seen, last_seen, metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 1, NOW(), NOW(), %s::jsonb)
                    ON CONFLICT (source_channel_id, target_channel_id, relation_type)
                    DO UPDATE SET
                        occurrence_count = channel_edges.occurrence_count + 1,
                        last_seen = NOW(),
                        source_platform = EXCLUDED.source_platform,
                        target_platform = EXCLUDED.target_platform,
                        evidence = CASE WHEN EXCLUDED.evidence != '' THEN EXCLUDED.evidence ELSE channel_edges.evidence END,
                        confidence = LEAST(100, channel_edges.confidence + 5),
                        metadata = channel_edges.metadata || EXCLUDED.metadata;
                """, (
                    source_lead_id, target_lead_id, relationship.relation_type,
                    relationship.source_platform, relationship.target_platform,
                    relationship.confidence, relationship.evidence[:1000], meta_json
                ))
            self.db.commit()
            return True
        except Exception as err:
            logger.warning(f"Error recording cross-platform edge ({relationship.source_canonical_id} -> {relationship.target_canonical_id}): {err}")
            try:
                self.db.rollback()
            except Exception:
                pass
            return False

    def get_cross_platform_network(self, canonical_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Retrieves in-degree and out-degree connected entities across all platforms.
        """
        if not self.db or not canonical_id:
            return []

        try:
            with self.db.cursor() as cur:
                cur.execute("""
                    SELECT 
                        ce.relation_type, ce.source_platform, ce.target_platform,
                        ce.confidence, ce.occurrence_count, ce.last_seen, ce.evidence,
                        l_target.canonical_id as target_canonical_id,
                        l_target.channel_username as target_username,
                        l_target.platform as target_platform_name,
                        l_target.member_count as target_members,
                        l_target.lead_score as target_score
                    FROM channel_edges ce
                    JOIN leads l_source ON ce.source_channel_id = l_source.id
                    JOIN leads l_target ON ce.target_channel_id = l_target.id
                    WHERE l_source.canonical_id = %s
                    ORDER BY ce.occurrence_count DESC, ce.last_seen DESC
                    LIMIT %s;
                """, (canonical_id, limit))
                cols = [desc[0] for desc in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as err:
            logger.warning(f"Error querying cross-platform network: {err}")
            return []
