"""
app/discovery/cross_platform_engine.py — Unified Multi-Platform Autonomous Discovery Engine

Coordinates free, cross-platform discovery across Telegram, TikTok, Facebook,
and the public Web with rate limiting, failure isolation, recursive multi-hop spidering,
candidate relevance verification, bridge query execution, and priority routing.
"""

import json
import random
import asyncio
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

from app.discovery.entity_model import (
    Platform, EntityType, RelationType, CanonicalIdentity,
    DiscoveredEntity, DiscoveredRelationship, DiscoveryCandidate,
    CandidateStatus, GENERIC_DOMAIN_BLACKLIST, GENERIC_HANDLE_BLACKLIST,
    evaluate_candidate_relevance
)
from app.discovery.connectors.base import BaseDiscoveryConnector
from app.discovery.connectors.tiktok import TikTokDiscoveryConnector
from app.discovery.connectors.facebook import FacebookDiscoveryConnector
from app.discovery.connectors.web import WebDiscoveryConnector
from app.discovery.connectors.telegram import TelegramDiscoveryConnector
from app.discovery.query_generator import QueryGenerator
from app.graph.cross_platform_graph import CrossPlatformGraphManager
from app.discovery.recursive_spider import RecursiveSpider
from app.discovery.provenance import ProvenanceManager

logger = logging.getLogger(__name__)


class CrossPlatformDiscoveryEngine:
    """
    Main orchestrator for autonomous cross-platform discovery.
    Coordinates connectors, candidate verification, graph persistence,
    recursive spider traversal, bridge queries, and queue consumers.
    """

    def __init__(
        self,
        redis_conn,
        db_conn=None,
        query_generator: Optional[QueryGenerator] = None
    ):
        self.redis = redis_conn
        self.db = db_conn
        self.query_gen = query_generator or QueryGenerator()

        # Initialize Connectors
        self.connectors: Dict[str, BaseDiscoveryConnector] = {
            Platform.WEB: WebDiscoveryConnector(),
            Platform.TIKTOK: TikTokDiscoveryConnector(),
            Platform.FACEBOOK: FacebookDiscoveryConnector(),
            Platform.TELEGRAM: TelegramDiscoveryConnector()
        }

        # Initialize Graph & Provenance Managers
        self.graph_mgr = CrossPlatformGraphManager(db_conn=self.db, redis_conn=self.redis)
        self.provenance_mgr = ProvenanceManager(redis_conn=self.redis, db_conn=self.db) if self.redis else None

        # Initialize Recursive Spider
        self.spider = RecursiveSpider(
            redis_conn=self.redis,
            db_conn=self.db,
            connectors=self.connectors,
            graph_manager=self.graph_mgr,
            provenance_manager=self.provenance_mgr,
            max_depth=4
        )

        self.stats = {
            "total_cycles": 0,
            "telegram_discovered": 0,
            "tiktok_discovered": 0,
            "facebook_discovered": 0,
            "web_discovered": 0,
            "edges_recorded": 0,
            "bridge_queries_executed": 0,
            "spider_hops_executed": 0,
            "queue_candidates_processed": 0
        }

    def is_backpressure_active(self, threshold: int = 1500) -> bool:
        """Checks if validation queues are currently backed up."""
        if not self.redis:
            return False
        try:
            q_len = self.redis.llen("queue:normal") + self.redis.llen("queue:high")
            return q_len >= threshold
        except Exception:
            return False

    def enqueue_telegram_lead(self, username_or_link: str, source_tag: str, keyword: str = "") -> bool:
        """
        Deduplicates and enqueues a discovered Telegram channel into the validator priority queues.
        Uses atomic Redis primitives to eliminate race conditions.
        """
        if not self.redis or not username_or_link:
            return False

        clean_u = CanonicalIdentity.clean_telegram(username_or_link)
        if not clean_u or clean_u in GENERIC_HANDLE_BLACKLIST or clean_u.endswith("bot") or len(clean_u) < 4:
            return False

        # Atomic deduplication check in Redis (1 day TTL)
        dedup_key = f"spider:enqueued:telegram:{clean_u}"
        is_new_redis = self.redis.set(dedup_key, 1, nx=True, ex=86400)
        if not is_new_redis:
            return False

        is_new = True
        count = 1
        sources = [source_tag]

        if self.provenance_mgr:
            try:
                is_new, count, sources = self.provenance_mgr.record_candidate_discovery(
                    username_or_link=clean_u,
                    source_type=source_tag,
                    keyword=keyword
                )
            except Exception:
                pass

        payload = json.dumps({
            "username": clean_u,
            "link": f"https://t.me/{clean_u}",
            "source": source_tag,
            "method": "cross_platform_spider",
            "keyword": keyword,
            "discovered_count": count,
            "sources": sources
        })
        self.redis.rpush("queue:normal", payload)
        self.stats["telegram_discovered"] += 1
        logger.info(f"✨ [DISCOVERY] Enqueued new Telegram channel @{clean_u} via {source_tag} (query: '{keyword}')")
        return True

    def process_candidate_verification(self, entity: DiscoveredEntity) -> Tuple[bool, DiscoveredEntity]:
        """
        Passes a non-Telegram candidate through real entity verification and relevance scoring:
        Candidate -> Entity Resolution -> Reachability/Bio Fetch -> Forex Relevance Scoring.
        Returns: (is_relevant: bool, updated_entity: DiscoveredEntity)
        """
        if entity.platform == Platform.TELEGRAM:
            return True, entity

        # Check domain / handle blacklist
        if entity.platform == Platform.WEB:
            domain = entity.username or entity.canonical_id.replace("web:", "")
            if domain in GENERIC_DOMAIN_BLACKLIST or any(domain.endswith('.' + b) or domain == b for b in GENERIC_DOMAIN_BLACKLIST):
                entity.metadata["relevance_score"] = 0
                entity.metadata["is_relevant"] = False
                entity.metadata["rejection_reason"] = "generic_domain_blacklist"
                return False, entity

        if entity.username and entity.username in GENERIC_HANDLE_BLACKLIST:
            entity.metadata["relevance_score"] = 0
            entity.metadata["is_relevant"] = False
            entity.metadata["rejection_reason"] = "generic_handle_blacklist"
            return False, entity

        # If already evaluated with relevance score
        if "is_relevant" in entity.metadata:
            return entity.metadata["is_relevant"], entity

        # Fetch and verify content via appropriate connector
        connector = self.connectors.get(entity.platform)
        if not connector or not connector.is_healthy():
            # Conservative: cannot verify without connector
            entity.metadata["relevance_score"] = 0
            entity.metadata["is_relevant"] = False
            entity.metadata["rejection_reason"] = "connector_unavailable"
            return False, entity

        try:
            if entity.platform == Platform.TIKTOK:
                clean_u = entity.username or entity.canonical_id.replace("tiktok:", "")
                main_ent, relations, cross_ents = connector.inspect_public_profile(clean_u)
                if main_ent:
                    entity = main_ent
            elif entity.platform == Platform.FACEBOOK:
                clean_slug = entity.username or entity.canonical_id.replace("facebook:", "")
                main_ent, relations, cross_ents = connector.inspect_public_page(clean_slug)
                if main_ent:
                    entity = main_ent
            elif entity.platform == Platform.WEB:
                if entity.url:
                    main_ent, relations, cross_ents = connector.crawl_website_for_bridges(entity.url)
                    if main_ent:
                        entity = main_ent
        except Exception as ver_err:
            logger.debug(f"Candidate verification error for {entity.canonical_id}: {ver_err}")

        # Compute relevance if not yet attached
        is_rel = entity.metadata.get("is_relevant", False)
        if "is_relevant" not in entity.metadata:
            is_rel, rel_score, terms = evaluate_candidate_relevance(
                entity.title or "",
                entity.description or "",
                entity.raw_content or ""
            )
            entity.metadata["is_relevant"] = is_rel
            entity.metadata["relevance_score"] = rel_score
            entity.metadata["matched_terms"] = terms

        return is_rel, entity

    async def process_cross_platform_queue(self, max_items: int = 5) -> int:
        """
        Consumes candidates from queue:cross_platform, verifies their relevance,
        persists valid entities to leads & graph edges, and triggers recursive spider hops.
        Failed or repeatedly malformed items are routed to dlq:cross_platform.
        """
        if not self.redis:
            return 0

        processed = 0
        for _ in range(max_items):
            try:
                raw_item = self.redis.lpop("queue:cross_platform")
                if not raw_item:
                    break

                item_data = json.loads(raw_item)
                canonical_id = item_data.get("canonical_id")
                platform = item_data.get("platform")
                if not canonical_id or not platform:
                    continue

                entity = DiscoveredEntity(
                    platform=platform,
                    entity_type=item_data.get("entity_type", EntityType.ACCOUNT),
                    canonical_id=canonical_id,
                    username=item_data.get("username"),
                    title=item_data.get("title"),
                    description=item_data.get("description"),
                    url=item_data.get("url", ""),
                    metadata=item_data.get("metadata", {}),
                    depth=item_data.get("depth", 1)
                )

                # 1. Candidate Verification & Relevance Scoring
                is_relevant, verified_entity = self.process_candidate_verification(entity)

                # 2. Persist to leads table (status 'verified' if relevant, 'rejected' otherwise)
                self.graph_mgr.ensure_entity_lead(verified_entity)

                # 3. If relevant, expand recursively via Spider
                if is_relevant and verified_entity.depth < 4:
                    new_discoveries = self.spider.expand_entity_hop(verified_entity)
                    self.stats["spider_hops_executed"] += 1
                    for child in new_discoveries:
                        if child.platform == Platform.TELEGRAM:
                            self.enqueue_telegram_lead(child.username or child.canonical_id, f"spider_hop:{canonical_id}")

                processed += 1
                self.stats["queue_candidates_processed"] += 1

            except json.JSONDecodeError:
                # Malformed JSON to DLQ
                if self.redis and raw_item:
                    self.redis.rpush("dlq:cross_platform", raw_item)
            except Exception as err:
                logger.warning(f"Error processing cross-platform queue item: {err}")

        return processed

    async def run_discovery_cycle(self, shutdown_event: Optional[asyncio.Event] = None) -> Dict[str, Any]:
        """
        Executes a complete, integrated cross-platform discovery cycle:
        1. Backpressure Guard.
        2. Query Generation (Direct & Cross-Platform Bridge Queries).
        3. Web, TikTok, Facebook organic candidate ingestion.
        4. Cross-Platform Bridge Query Execution (Web <-> Telegram <-> TikTok <-> Facebook).
        5. Recursive Spider Hop Expansion for discovered relevant entities.
        6. Cross-Platform Queue Processing (verification, relevance, DLQ routing).
        7. Telemetry & Health synchronization.
        """
        self.stats["total_cycles"] += 1
        logger.info(f"🚀 Starting Unified Spider-Web Discovery cycle #{self.stats['total_cycles']}...")

        # 1. Backpressure guard
        while self.is_backpressure_active() and (not shutdown_event or not shutdown_event.is_set()):
            logger.warning("Discovery paused due to high validation queue backpressure. Waiting 30s...")
            if shutdown_event:
                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=30)
                except asyncio.TimeoutError:
                    pass
            else:
                await asyncio.sleep(30)

        # 2. Generate balanced queries across platforms and bridges
        web_queries = self.query_gen.generate_queries_for_platform(Platform.WEB, limit=6)
        tiktok_queries = self.query_gen.generate_queries_for_platform(Platform.TIKTOK, limit=5)
        facebook_queries = self.query_gen.generate_queries_for_platform(Platform.FACEBOOK, limit=5)
        bridge_queries = self.query_gen.generate_cross_platform_bridge_queries(limit=6)

        cycle_results = {
            "web_entities": 0,
            "tiktok_entities": 0,
            "facebook_entities": 0,
            "telegram_enqueued": 0,
            "edges_created": 0,
            "spider_expansions": 0,
            "queue_processed": 0
        }

        # ── 3. Execute Web & Directory Discovery ─────────────────────────────
        web_conn = self.connectors[Platform.WEB]
        if web_conn.is_healthy():
            for query in web_queries:
                if shutdown_event and shutdown_event.is_set():
                    break
                try:
                    res = web_conn.search(query)
                    cycle_results["web_entities"] += len(res.entities)
                    self.stats["web_discovered"] += len(res.entities)

                    for ent in res.entities:
                        if ent.platform == Platform.TELEGRAM:
                            if self.enqueue_telegram_lead(ent.username or ent.canonical_id, f"web:{query}", query):
                                cycle_results["telegram_enqueued"] += 1
                        else:
                            is_rel, verified_ent = self.process_candidate_verification(ent)
                            self.graph_mgr.ensure_entity_lead(verified_ent)
                            if is_rel and verified_ent.depth < 3:
                                children = self.spider.expand_entity_hop(verified_ent)
                                cycle_results["spider_expansions"] += 1
                                for ch in children:
                                    if ch.platform == Platform.TELEGRAM:
                                        self.enqueue_telegram_lead(ch.username or ch.canonical_id, f"spider:{verified_ent.canonical_id}")

                    for rel in res.relationships:
                        if self.graph_mgr.record_cross_platform_edge(rel):
                            cycle_results["edges_created"] += 1
                            self.stats["edges_recorded"] += 1

                    await asyncio.sleep(web_conn.get_jittered_delay())
                except Exception as err:
                    logger.debug(f"[CrossPlatformEngine] Web query '{query}' notice: {err}")

        # ── 4. Execute TikTok Discovery ──────────────────────────────────────
        tt_conn = self.connectors[Platform.TIKTOK]
        if tt_conn.is_healthy():
            for query in tiktok_queries:
                if shutdown_event and shutdown_event.is_set():
                    break
                try:
                    res = tt_conn.search(query)
                    cycle_results["tiktok_entities"] += len(res.entities)
                    self.stats["tiktok_discovered"] += len(res.entities)

                    for ent in res.entities:
                        if ent.platform == Platform.TELEGRAM:
                            if self.enqueue_telegram_lead(ent.username or ent.canonical_id, f"tiktok_bio:{query}", query):
                                cycle_results["telegram_enqueued"] += 1
                        else:
                            is_rel, verified_ent = self.process_candidate_verification(ent)
                            self.graph_mgr.ensure_entity_lead(verified_ent)
                            if is_rel and verified_ent.depth < 3:
                                children = self.spider.expand_entity_hop(verified_ent)
                                cycle_results["spider_expansions"] += 1
                                for ch in children:
                                    if ch.platform == Platform.TELEGRAM:
                                        self.enqueue_telegram_lead(ch.username or ch.canonical_id, f"spider:{verified_ent.canonical_id}")

                    for rel in res.relationships:
                        if self.graph_mgr.record_cross_platform_edge(rel):
                            cycle_results["edges_created"] += 1
                            self.stats["edges_recorded"] += 1

                    await asyncio.sleep(tt_conn.get_jittered_delay())
                except Exception as err:
                    logger.debug(f"[CrossPlatformEngine] TikTok query '{query}' notice: {err}")

        # ── 5. Execute Facebook Discovery ────────────────────────────────────
        fb_conn = self.connectors[Platform.FACEBOOK]
        if fb_conn.is_healthy():
            for query in facebook_queries:
                if shutdown_event and shutdown_event.is_set():
                    break
                try:
                    res = fb_conn.search(query)
                    cycle_results["facebook_entities"] += len(res.entities)
                    self.stats["facebook_discovered"] += len(res.entities)

                    for ent in res.entities:
                        if ent.platform == Platform.TELEGRAM:
                            if self.enqueue_telegram_lead(ent.username or ent.canonical_id, f"facebook_page:{query}", query):
                                cycle_results["telegram_enqueued"] += 1
                        else:
                            is_rel, verified_ent = self.process_candidate_verification(ent)
                            self.graph_mgr.ensure_entity_lead(verified_ent)
                            if is_rel and verified_ent.depth < 3:
                                children = self.spider.expand_entity_hop(verified_ent)
                                cycle_results["spider_expansions"] += 1
                                for ch in children:
                                    if ch.platform == Platform.TELEGRAM:
                                        self.enqueue_telegram_lead(ch.username or ch.canonical_id, f"spider:{verified_ent.canonical_id}")

                    for rel in res.relationships:
                        if self.graph_mgr.record_cross_platform_edge(rel):
                            cycle_results["edges_created"] += 1
                            self.stats["edges_recorded"] += 1

                    await asyncio.sleep(fb_conn.get_jittered_delay())
                except Exception as err:
                    logger.debug(f"[CrossPlatformEngine] Facebook query '{query}' notice: {err}")

        # ── 6. Execute Cross-Platform Bridge Queries (Web <-> Telegram <-> TikTok) ─
        for b_query in bridge_queries:
            if shutdown_event and shutdown_event.is_set():
                break
            if web_conn.is_healthy():
                try:
                    res = web_conn.search(b_query)
                    self.stats["bridge_queries_executed"] += 1

                    for ent in res.entities:
                        if ent.platform == Platform.TELEGRAM:
                            if self.enqueue_telegram_lead(ent.username or ent.canonical_id, f"bridge:{b_query}", b_query):
                                cycle_results["telegram_enqueued"] += 1
                        else:
                            is_rel, verified_ent = self.process_candidate_verification(ent)
                            self.graph_mgr.ensure_entity_lead(verified_ent)
                            if is_rel:
                                children = self.spider.expand_entity_hop(verified_ent)
                                cycle_results["spider_expansions"] += 1
                                for ch in children:
                                    if ch.platform == Platform.TELEGRAM:
                                        self.enqueue_telegram_lead(ch.username or ch.canonical_id, f"bridge_spider:{verified_ent.canonical_id}")

                    for rel in res.relationships:
                        if self.graph_mgr.record_cross_platform_edge(rel):
                            cycle_results["edges_created"] += 1
                            self.stats["edges_recorded"] += 1

                    await asyncio.sleep(web_conn.get_jittered_delay())
                except Exception as b_err:
                    logger.debug(f"[CrossPlatformEngine] Bridge query '{b_query}' notice: {b_err}")

        # ── 7. Process Cross-Platform Queue (Consumer + Spider Expansion) ─────
        q_count = await self.process_cross_platform_queue(max_items=8)
        cycle_results["queue_processed"] = q_count

        # ── 8. Update Redis Telemetry ────────────────────────────────────────
        if self.redis:
            try:
                self.redis.set("discovery:cross_platform:stats", json.dumps(self.stats), ex=86400)
                for plat, conn in self.connectors.items():
                    health_payload = {
                        "status": conn.health.status,
                        "consecutive_failures": conn.health.consecutive_failures,
                        "total_requests": conn.health.total_requests,
                        "total_successes": conn.health.total_successes,
                        "total_discovered": conn.health.total_entities_discovered,
                        "last_success_at": conn.health.last_success_at.isoformat() if conn.health.last_success_at else None
                    }
                    self.redis.set(f"health:connector:{plat}:status", json.dumps(health_payload), ex=3600)
            except Exception as e:
                logger.debug(f"Redis telemetry update notice: {e}")

        logger.info(
            f"✅ Unified Spider-Web Discovery cycle #{self.stats['total_cycles']} finished: "
            f"{cycle_results['telegram_enqueued']} Telegram leads enqueued, "
            f"{cycle_results['edges_created']} graph edges created, "
            f"{cycle_results['spider_expansions']} spider hops, "
            f"{cycle_results['queue_processed']} cross-platform queue jobs processed."
        )

        return cycle_results
