"""
app/discovery/cross_platform_engine.py — Unified Multi-Platform Discovery Engine

Coordinates free, cross-platform discovery across Telegram, TikTok, Facebook,
and the public Web with rate limiting, failure isolation, recursive graph expansion,
and automatic enqueueing into the core LeadHunter discovery pipeline.
"""

import json
import random
import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from app.discovery.entity_model import (
    Platform, EntityType, RelationType, CanonicalIdentity,
    DiscoveredEntity, DiscoveredRelationship
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
    Main orchestrator for free cross-platform discovery.
    Coordinates connectors, graph persistence, provenance, and queue routing.
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
            "edges_recorded": 0
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
        Deduplicates and enqueues a discovered Telegram channel into the existing validator queues.
        """
        if not self.redis or not username_or_link:
            return False

        clean_u = CanonicalIdentity.clean_telegram(username_or_link)
        GENERIC_IGNORES = {
            "joinchat", "share", "addlist", "bot", "username", "contact",
            "channel", "group", "admin", "help", "support", "login", "home",
            "privacy", "terms", "about", "rules", "faq", "proxy", "socks"
        }
        if not clean_u or clean_u in GENERIC_IGNORES or clean_u.endswith("bot") or len(clean_u) < 4:
            return False

        is_new = True
        count = 1
        sources = [source_tag]

        if self.provenance_mgr:
            is_new, count, sources = self.provenance_mgr.record_candidate_discovery(
                username_or_link=clean_u,
                source_type=source_tag,
                keyword=keyword
            )

        if is_new:
            payload = json.dumps({
                "username": clean_u,
                "link": f"https://t.me/{clean_u}",
                "source": source_tag,
                "method": "cross_platform",
                "keyword": keyword,
                "discovered_count": count,
                "sources": sources
            })
            self.redis.rpush("queue:normal", payload)
            self.stats["telegram_discovered"] += 1
            logger.info(f"✨ [DISCOVERY] Enqueued new Telegram channel @{clean_u} via {source_tag} (query: '{keyword}')")
            return True

        return False

    async def run_discovery_cycle(self, shutdown_event: Optional[asyncio.Event] = None) -> Dict[str, Any]:
        """
        Executes a complete cross-platform discovery cycle across Web, TikTok, and Facebook.
        """
        self.stats["total_cycles"] += 1
        logger.info(f"🚀 Starting Cross-Platform Discovery cycle #{self.stats['total_cycles']}...")

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

        # 2. Generate balanced queries across platforms
        web_queries = self.query_gen.generate_queries_for_platform(Platform.WEB, limit=8)
        tiktok_queries = self.query_gen.generate_queries_for_platform(Platform.TIKTOK, limit=6)
        facebook_queries = self.query_gen.generate_queries_for_platform(Platform.FACEBOOK, limit=6)
        bridge_queries = self.query_gen.generate_cross_platform_bridge_queries(limit=5)

        cycle_results = {
            "web_entities": 0,
            "tiktok_entities": 0,
            "facebook_entities": 0,
            "telegram_enqueued": 0,
            "edges_created": 0
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
                            # Save non-telegram entity to leads
                            self.graph_mgr.ensure_entity_lead(ent)

                    # Record relationship edges
                    for rel in res.relationships:
                        if self.graph_mgr.record_cross_platform_edge(rel):
                            cycle_results["edges_created"] += 1
                            self.stats["edges_recorded"] += 1

                    # Jitter delay
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
                            self.graph_mgr.ensure_entity_lead(ent)

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
                            self.graph_mgr.ensure_entity_lead(ent)

                    for rel in res.relationships:
                        if self.graph_mgr.record_cross_platform_edge(rel):
                            cycle_results["edges_created"] += 1
                            self.stats["edges_recorded"] += 1

                    await asyncio.sleep(fb_conn.get_jittered_delay())
                except Exception as err:
                    logger.debug(f"[CrossPlatformEngine] Facebook query '{query}' notice: {err}")

        # ── 6. Update Redis Telemetry ────────────────────────────────────────
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
            f"✅ Cross-Platform Discovery cycle finished: "
            f"{cycle_results['telegram_enqueued']} Telegram leads enqueued, "
            f"{cycle_results['edges_created']} graph edges created."
        )

        return cycle_results
