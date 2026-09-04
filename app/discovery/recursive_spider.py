"""
app/discovery/recursive_spider.py — Cross-Platform Recursive Spider Engine

Traverses multi-hop entity chains across Telegram, TikTok, Facebook, and Web:
e.g. Telegram -> TikTok -> Website -> Facebook -> Telegram.
Enforces loop prevention via canonical identities, Redis visited sets,
depth limits, and crawl budgets without dropping small or inactive entities.
"""

import json
import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from datetime import datetime, timezone

from app.discovery.entity_model import (
    Platform, EntityType, RelationType, CanonicalIdentity,
    DiscoveredEntity, DiscoveredRelationship
)
from app.discovery.connectors.base import BaseDiscoveryConnector
from app.graph.cross_platform_graph import CrossPlatformGraphManager
from app.discovery.provenance import ProvenanceManager

logger = logging.getLogger(__name__)

DEFAULT_MAX_DEPTH = 4
DEFAULT_SPIDER_BUDGET_PER_HOP = 10
VISITED_TTL_SECONDS = 604800  # 7 days


class RecursiveSpider:
    """
    Multi-hop spider exploring cross-platform relationships recursively.
    """

    def __init__(
        self,
        redis_conn,
        db_conn,
        connectors: Dict[str, BaseDiscoveryConnector],
        graph_manager: CrossPlatformGraphManager,
        provenance_manager: Optional[ProvenanceManager] = None,
        max_depth: int = DEFAULT_MAX_DEPTH,
        budget_per_hop: int = DEFAULT_SPIDER_BUDGET_PER_HOP
    ):
        self.redis = redis_conn
        self.db = db_conn
        self.connectors = connectors
        self.graph_mgr = graph_manager
        self.provenance_mgr = provenance_manager
        self.max_depth = max_depth
        self.budget_per_hop = budget_per_hop

    def is_visited(self, canonical_id: str) -> bool:
        """Checks if an entity canonical ID has already been crawled in the current cycle."""
        if not self.redis or not canonical_id:
            return False
        try:
            return bool(self.redis.exists(f"spider:visited:{canonical_id}"))
        except Exception:
            return False

    def mark_visited(self, canonical_id: str, depth: int) -> None:
        """Marks an entity as visited with TTL and records the visit depth."""
        if not self.redis or not canonical_id:
            return
        try:
            key = f"spider:visited:{canonical_id}"
            self.redis.set(key, depth, ex=VISITED_TTL_SECONDS)
        except Exception:
            pass

    def enqueue_for_validation(self, entity: DiscoveredEntity) -> bool:
        """
        Routes newly discovered candidates to the appropriate Redis queue.
        Telegram entities go to queue:normal or queue:high for the validator.
        Cross-platform entities go to queue:cross_platform.
        """
        if not self.redis or not entity.canonical_id:
            return False

        try:
            if entity.platform == Platform.TELEGRAM:
                # Telegram channels go to standard validator queues
                clean_u = entity.username or entity.canonical_id.replace("telegram:", "")
                payload = json.dumps({
                    "username": clean_u,
                    "link": entity.url or f"https://t.me/{clean_u}",
                    "source": entity.metadata.get("source", "cross_platform_spider"),
                    "method": "spider_hop",
                    "depth": entity.depth
                })
                # If discovered via a high-value bridge (e.g. direct VIP TikTok profile), route to queue:high
                q_name = "queue:high" if entity.depth <= 1 else "queue:normal"
                self.redis.rpush(q_name, payload)
                logger.info(f"🕸️ [SPIDER] Queued Telegram candidate @{clean_u} to {q_name} (depth={entity.depth})")
                return True
            else:
                # TikTok, Facebook, Web candidates go to cross-platform spider queue
                payload = json.dumps(entity.to_dict())
                self.redis.rpush("queue:cross_platform", payload)
                logger.info(f"🕸️ [SPIDER] Queued {entity.platform} candidate {entity.canonical_id} to queue:cross_platform")
                return True
        except Exception as err:
            logger.warning(f"Failed to enqueue candidate {entity.canonical_id}: {err}")
            return False

    def expand_entity_hop(
        self,
        entity: DiscoveredEntity,
        parent_canonical: Optional[str] = None
    ) -> List[DiscoveredEntity]:
        """
        Recursively processes an entity:
        1. Ensures entity exists in leads table.
        2. Inspects content for outbound bridges.
        3. Records cross-platform edges in channel_edges.
        4. Enqueues new child discoveries up to max_depth.
        """
        if not entity.canonical_id:
            return []

        # Depth check: stop recursion if exceeding max_depth
        if entity.depth > self.max_depth:
            logger.debug(f"[SPIDER] Depth {entity.depth} exceeds limit {self.max_depth} for {entity.canonical_id}. Stopping branch.")
            return []

        # Ensure entity lead exists
        self.graph_mgr.ensure_entity_lead(entity)

        # Track provenance
        if self.provenance_mgr:
            try:
                self.provenance_mgr.record_candidate_discovery(
                    username_or_link=entity.canonical_id,
                    source_type=f"{entity.platform}_spider",
                    referrer_channel_id=parent_canonical
                )
            except Exception:
                pass

        # Loop check: if visited, we don't re-crawl content to prevent loops
        if self.is_visited(entity.canonical_id):
            return []

        self.mark_visited(entity.canonical_id, entity.depth)

        # Select appropriate connector to inspect outbound links
        connector = self.connectors.get(entity.platform)
        if not connector or not connector.is_healthy():
            return []

        outbound_entities: List[DiscoveredEntity] = []
        outbound_relations: List[DiscoveredRelationship] = []

        try:
            if entity.platform == Platform.TIKTOK:
                clean_u = entity.username or entity.canonical_id.replace("tiktok:", "")
                _, relations, cross_ents = connector.inspect_public_profile(clean_u)
                outbound_entities.extend(cross_ents)
                outbound_relations.extend(relations)

            elif entity.platform == Platform.FACEBOOK:
                clean_slug = entity.username or entity.canonical_id.replace("facebook:", "")
                _, relations, cross_ents = connector.inspect_public_page(clean_slug)
                outbound_entities.extend(cross_ents)
                outbound_relations.extend(relations)

            elif entity.platform == Platform.WEB:
                if entity.url:
                    _, relations, cross_ents = connector.crawl_website_for_bridges(entity.url)
                    outbound_entities.extend(cross_ents)
                    outbound_relations.extend(relations)

        except Exception as hop_err:
            logger.debug(f"[SPIDER] Error expanding {entity.canonical_id}: {hop_err}")

        # Process discovered bridges up to budget
        new_discoveries: List[DiscoveredEntity] = []
        for child in outbound_entities[:self.budget_per_hop]:
            child.depth = entity.depth + 1

            # Record directed edge in the cross-platform graph
            rel = DiscoveredRelationship(
                source_canonical_id=entity.canonical_id,
                target_canonical_id=child.canonical_id,
                source_platform=entity.platform,
                target_platform=child.platform,
                relation_type=RelationType.LINK if child.platform == Platform.TELEGRAM else RelationType.SOCIAL_LINK,
                confidence=90,
                evidence=f"Discovered via {entity.platform} spider hop from {entity.canonical_id}"
            )
            self.graph_mgr.record_cross_platform_edge(rel, source_entity=entity, target_entity=child)

            # Route to queues
            self.enqueue_for_validation(child)
            new_discoveries.append(child)

        return new_discoveries
