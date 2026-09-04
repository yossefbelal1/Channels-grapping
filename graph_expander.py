"""
graph_expander.py — Production Multi-Edge Graph Intelligence Engine (Worker D)

Continuously reads validated channels and groups from PostgreSQL,
fetches recent posts, analyzes forwards, mentions, links, and promo patterns,
builds the multi-edge graph in `channel_edges`, and pushes high-priority
new discoveries into the validation queues.
"""

import os
import sys
import re
import json
import asyncio
import signal
import logging
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import redis
from telethon.tl.types import Chat, Channel
from tg_manager import TelegramManager
from validator import DatabaseHelper, normalize_telegram_link, parse_telegram_link

# Graph & Provenance Modules
from app.graph.edge_manager import GraphEdgeManager, EdgeRelation
from app.graph.forward_analyzer import ForwardAnalyzer
from app.graph.graph_importance import GraphImportanceCalculator
from app.scheduler.watermark_manager import WatermarkManager
from app.discovery.provenance import ProvenanceManager

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [GRAPH] [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

TELEGRAM_LINK_REGEX = re.compile(
    r'(?:https?://)?(?:t\.me|telegram\.me)/(?:joinchat/)?\+?[a-zA-Z0-9_.-]+',
    re.IGNORECASE
)
USERNAME_REGEX = re.compile(r'@([a-zA-Z0-9_]{5,32})')

JUNK_USERNAMES = {
    'joinchat', 'share', 'addstickers', 'addlist', 'gmail', 'hotmail',
    'yahoo', 'outlook', 'icloud', 'mail', 'yandex', 'protonmail', 'proton',
    'telegram', 'spambot', 'sticker', 'gif', 'bot', 'username', 'ads',
    'advertise', 'channel', 'group', 'chat', 'support', 'help', 'admin',
    'contact', 'info', 'service', 'feedback', 'terms', 'privacy'
}

PROMO_KEYWORDS = ["تبادل", "إعلان", "اشتركوا", "انضموا", "قناتنا", "برعاية", "vip", "توصيات"]


class GraphExpander:
    """
    Multi-Edge Graph Intelligence & Forward Origin Analyzer.
    """

    def __init__(self):
        load_dotenv()

        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.redis_db = int(os.getenv("REDIS_DB", 0))
        self.redis_password = os.getenv("REDIS_PASSWORD", None)

        self.db_host = os.getenv("DB_HOST", "localhost")
        self.db_port = int(os.getenv("DB_PORT", 5432))
        self.db_name = os.getenv("DB_NAME", "leadhunter_db")
        self.db_user = os.getenv("DB_USER", "postgres")
        self.db_password = os.getenv("DB_PASSWORD", "")

        self.session_name = os.getenv("SESSION_GRAPH_EXPANDER", "graph_expander_session")
        self.post_limit = int(os.getenv("GRAPH_EXPANDER_POST_LIMIT", 300))
        self.channel_interval = int(os.getenv("GRAPH_EXPANDER_INTERVAL_SECONDS", 180))
        self.max_depth = int(os.getenv("GRAPH_MAX_DEPTH", 6))
        self.batch_size = int(os.getenv("GRAPH_EXPANDER_BATCH_SIZE", 20))

        self.redis_conn = None
        self.db_helper = None
        self.tg_manager = None
        self.edge_mgr = None
        self.provenance_mgr = None
        self.shutdown_event = asyncio.Event()

    def get_channels_for_expansion(self, batch_size: int = 20) -> list:
        """Pulls priority leads ready for graph traversal."""
        self.db_helper.check_connection()
        query = """
        SELECT id, channel_username, lead_score, depth, is_group
        FROM leads
        WHERE status != 'rejected'
          AND (description IS NULL OR (description NOT LIKE 'Blacklisted entity%%' AND description NOT LIKE 'Entity does not exist%%'))
          AND (depth IS NULL OR depth < %s)
          AND (last_graph_scan IS NULL OR last_graph_scan < NOW() - INTERVAL '3 days')
        ORDER BY
          CASE WHEN last_graph_scan IS NULL THEN 1 ELSE 2 END,
          lead_score DESC NULLS LAST
        LIMIT %s;
        """
        try:
            with self.db_helper.conn.cursor() as cur:
                cur.execute(query, (self.max_depth, batch_size))
                return cur.fetchall() or []
        except Exception as e:
            logging.error(f"[GRAPH] Error fetching expansion candidates: {e}")
            return []

    def update_last_graph_scan(self, username: str):
        self.db_helper.check_connection()
        try:
            with self.db_helper.conn.cursor() as cur:
                cur.execute("UPDATE leads SET last_graph_scan = NOW() WHERE channel_username = %s", (username,))
            self.db_helper.conn.commit()
        except Exception as e:
            logging.warning(f"[GRAPH] Failed to update last_graph_scan for @{username}: {e}")

    def insert_or_get_target_lead(self, username: str, depth: int, source_username: str) -> str:
        """Upserts stub lead for newly discovered target."""
        self.db_helper.check_connection()
        try:
            query = """
            INSERT INTO leads (channel_username, status, discovered_at, depth, discovery_source, discovery_method)
            VALUES (%s, 'new', NOW(), %s, %s, 'graph')
            ON CONFLICT (channel_username) DO UPDATE SET
                discovery_source = COALESCE(leads.discovery_source, EXCLUDED.discovery_source)
            RETURNING id;
            """
            with self.db_helper.conn.cursor() as cur:
                cur.execute(query, (username, depth, source_username))
                res = cur.fetchone()
                return str(res['id']) if res else str(self.db_helper.get_lead_id_by_username(username))
        except Exception as e:
            logging.warning(f"Failed to upsert lead @{username}: {e}")
            return str(self.db_helper.get_lead_id_by_username(username) or '')

    async def fetch_posts(self, entity, limit: int = 300) -> list:
        username = getattr(entity, 'username', str(getattr(entity, 'id', 'unknown'))).lower()
        watermark_key = f"graph:watermark:{username}"
        last_max_id = self.redis_conn.get(watermark_key)
        min_id = int(last_max_id) if last_max_id and str(last_max_id).isdigit() else 0

        async def fetch(cl):
            if min_id > 0:
                return await cl.get_messages(entity, limit=min(150, limit), min_id=min_id)
            return await cl.get_messages(entity, limit=limit)

        try:
            msgs = await self.tg_manager.execute_request(
                self.session_name, fetch, shutdown_event=self.shutdown_event
            )
            if msgs and len(msgs) > 0:
                max_msg_id = max(getattr(m, 'id', 0) for m in msgs)
                if max_msg_id > 0:
                    self.redis_conn.set(watermark_key, max_msg_id, ex=86400 * 30)
            return msgs or []
        except Exception as e:
            logging.error(f"[GRAPH] Failed to fetch posts from @{username}: {e}")
            return []

    async def expand_entity(self, row: dict) -> bool:
        username = row['channel_username']
        source_id = str(row['id'])
        parent_depth = int(row.get('depth') or 0)
        child_depth = parent_depth + 1

        logging.info(f"[GRAPH] Traversing @{username} (depth={parent_depth}, limit={self.post_limit})...")

        async def resolve(cl):
            return await cl.get_entity(username)

        entity = None
        try:
            entity = await self.tg_manager.execute_request(self.session_name, resolve, shutdown_event=self.shutdown_event)
        except Exception as e:
            logging.warning(f"[GRAPH] Could not resolve entity @{username}: {e}")
            self.update_last_graph_scan(username)
            return False

        if not entity:
            self.update_last_graph_scan(username)
            return False

        messages = await self.fetch_posts(entity, limit=self.post_limit)
        if not messages:
            self.update_last_graph_scan(username)
            return False

        # Forward analysis summary
        forward_summary = ForwardAnalyzer.summarize_forwards(messages)
        if forward_summary.get("forwarded_count", 0) > 0:
            logging.info(f"[GRAPH] @{username} has {forward_summary['forwarded_count']} forwards (ratio: {forward_summary['forward_ratio']})")

        discovered_edges = []

        for msg in messages:
            msg_text = getattr(msg, 'message', '') or ''
            
            # 1. Forward Origin Inspection (Hardened v7)
            fwd = ForwardAnalyzer.extract_forward_origin(msg)
            if fwd:
                target_ident = None
                if fwd.get("from_name"):
                    fwd_name = fwd["from_name"].strip()
                    if fwd_name and not (fwd_name.lower().endswith("bot") or fwd_name.lower().endswith("_bot")):
                        clean_fwd = normalize_telegram_link(fwd_name)
                        link_type, fwd_user = parse_telegram_link(clean_fwd)
                        target_ident = fwd_user or fwd_name
                elif fwd.get("channel_id"):
                    target_ident = fwd["channel_id"]
                elif fwd.get("peer_id"):
                    target_ident = fwd["peer_id"]

                if target_ident:
                    evidence_payload = fwd.get("evidence")
                    evidence_str = json.dumps(evidence_payload) if isinstance(evidence_payload, dict) else f"Forwarded message ID {getattr(msg, 'id', '')}"
                    discovered_edges.append({
                        "target_username": target_ident,
                        "relation": EdgeRelation.FORWARDED_FROM,
                        "evidence": evidence_str,
                        "confidence": 95
                    })

            # 2. Telegram Link Regex
            for raw_link in TELEGRAM_LINK_REGEX.findall(msg_text):
                clean = raw_link.rstrip('.,;)!"\'')
                normalized = normalize_telegram_link(clean)
                link_type, target_user = parse_telegram_link(normalized)
                if link_type == 'public' and target_user:
                    is_promo = any(kw in msg_text for kw in PROMO_KEYWORDS)
                    rel = EdgeRelation.PROMOTED if is_promo else EdgeRelation.LINKED
                    discovered_edges.append({
                        "target_username": target_user,
                        "relation": rel,
                        "evidence": msg_text[:200],
                        "confidence": 85 if is_promo else 75
                    })

            # 3. Mention Regex (@username)
            for mention in USERNAME_REGEX.findall(msg_text):
                m_lower = mention.lower()
                if m_lower not in JUNK_USERNAMES and not (m_lower.endswith("bot") or m_lower.endswith("_bot")):
                    discovered_edges.append({
                        "target_username": mention,
                        "relation": EdgeRelation.MENTION,
                        "evidence": msg_text[:200],
                        "confidence": 70
                    })

        # 4. Similar Channel Recommendations (Phase 2)
        # Target validated public broadcast channels (any member count 400 to 2M+)
        if getattr(entity, 'broadcast', False):
            try:
                logging.info(f"[GRAPH] Fetching similar channel recommendations for @{username}...")
                recs = await self.tg_manager.get_channel_recommendations(
                    channel_peer=entity,
                    session_name=self.session_name,
                    shutdown_event=self.shutdown_event
                )
                if recs and hasattr(recs, 'chats'):
                    for chat in recs.chats:
                        rec_username = getattr(chat, 'username', None)
                        if rec_username:
                            discovered_edges.append({
                                "target_username": rec_username,
                                "relation": EdgeRelation.RECOMMENDATION,
                                "evidence": "Telegram official recommendation",
                                "confidence": 90
                            })
            except Exception as e:
                logging.warning(f"[GRAPH] Failed to fetch channel recommendations for @{username}: {e}")

        # Process and persist all discovered relationships
        new_queued = 0
        for edge in discovered_edges:
            target_user = edge["target_username"]
            target_clean = target_user.lower()
            if target_clean == username.lower():
                continue

            target_id = self.insert_or_get_target_lead(target_user, child_depth, username)
            if target_id and source_id:
                self.edge_mgr.record_edge(
                    source_channel_id=source_id,
                    target_channel_id=target_id,
                    relation_type=edge["relation"],
                    confidence=edge["confidence"],
                    evidence=edge["evidence"]
                )

            # Record provenance
            is_new, count, sources = self.provenance_mgr.record_candidate_discovery(
                username_or_link=target_user,
                source_type="graph" if edge["relation"] != EdgeRelation.FORWARDED_FROM else "forwards",
                referrer_channel_id=source_id
            )

            # Check seen_channels
            channel_link = f"https://t.me/{target_user}"
            if is_new:
                self.redis_conn.sadd("seen_channels", channel_link)
                payload = json.dumps({
                    "link": channel_link,
                    "source": f"@{username}",
                    "method": "graph",
                    "relation": edge["relation"],
                    "depth": child_depth,
                    "discovered_count": count,
                    "sources": sources
                })
                self.redis_conn.rpush("queue:high", payload)
                new_queued += 1

        logging.info(f"[GRAPH] @{username} crawl complete: {len(messages)} posts -> {len(discovered_edges)} edges -> {new_queued} new candidates queued.")
        self.update_last_graph_scan(username)

        # Compute and update graph importance score (PART J)
        if hasattr(self, 'importance_calc') and self.importance_calc:
            self.importance_calc.compute_and_update_channel(source_id)

        return True

    async def process_recommendations_queue(self, max_items: int = 10) -> int:
        """
        Consumes channels queued to recommendations:queue, calls Telegram's
        get_channel_recommendations, records RECOMMENDATION edges in channel_edges,
        and pushes new candidates to queue:high.
        """
        if not self.redis_conn:
            return 0

        processed = 0
        for _ in range(max_items):
            if self.shutdown_event.is_set():
                break

            raw = self.redis_conn.lpop("recommendations:queue")
            if not raw:
                break

            try:
                data = json.loads(raw) if isinstance(raw, str) else raw
                target_user = data.get("username")
                source_ch_id = data.get("channel_id")
                if not target_user:
                    continue

                target_clean = str(target_user).lstrip('@').strip()
                logging.info(f"[GRAPH-REC] Processing recommendation request for @{target_clean}...")

                # Fetch entity
                async def resolve_peer(cl):
                    return await cl.get_entity(target_clean)

                entity = await self.tg_manager.execute_request(
                    self.session_name,
                    resolve_peer,
                    shutdown_event=self.shutdown_event
                )
                if not entity or not getattr(entity, 'broadcast', False):
                    continue

                # Fetch similar recommendations
                recs = await self.tg_manager.get_channel_recommendations(
                    channel_peer=entity,
                    session_name=self.session_name,
                    shutdown_event=self.shutdown_event
                )
                if not recs or not hasattr(recs, 'chats'):
                    continue

                new_queued = 0
                for chat in recs.chats:
                    rec_username = getattr(chat, 'username', None)
                    if not rec_username or rec_username.lower() == target_clean.lower():
                        continue

                    # Insert stub lead
                    target_id = self.insert_or_get_target_lead(rec_username, 1, target_clean)
                    if target_id and source_ch_id:
                        self.edge_mgr.record_edge(
                            source_channel_id=str(source_ch_id),
                            target_channel_id=str(target_id),
                            relation_type=EdgeRelation.RECOMMENDATION,
                            confidence=90,
                            evidence="Telegram official recommendation"
                        )

                    # Record provenance
                    channel_link = f"https://t.me/{rec_username}"
                    is_new = True
                    if self.provenance_mgr:
                        try:
                            is_new, count, sources = self.provenance_mgr.record_candidate_discovery(
                                username_or_link=channel_link,
                                source_type="recommendation",
                                referrer_channel_id=str(source_ch_id)
                            )
                        except Exception as prov_err:
                            logging.debug(f"[GRAPH-REC] Provenance error: {prov_err}")

                    # Deduplicate in seen_channels and enqueue to queue:high
                    if is_new and not self.redis_conn.sismember("seen_channels", channel_link):
                        self.redis_conn.sadd("seen_channels", channel_link)
                        payload = json.dumps({
                            "link": channel_link,
                            "source": f"@{target_clean}",
                            "method": "recommendation",
                            "relation": EdgeRelation.RECOMMENDATION,
                            "depth": 1,
                            "discovery_source": "telegram_recommendations"
                        })
                        self.redis_conn.rpush("queue:high", payload)
                        new_queued += 1

                logging.info(f"[GRAPH-REC] @{target_clean} recommendations complete: {len(recs.chats)} found -> {new_queued} new queued to queue:high")
                processed += 1
                await asyncio.sleep(1)
            except Exception as err:
                logging.warning(f"[GRAPH-REC] Error processing recommendation item: {err}")

        return processed

    async def run_expansion_cycle(self):
        # 1. First drain and process any freshly validated channels waiting for recommendations
        try:
            await self.process_recommendations_queue(max_items=10)
        except Exception as q_err:
            logging.warning(f"[GRAPH] Error draining recommendations:queue: {q_err}")

        # 2. Regular batch expansion from database
        rows = self.get_channels_for_expansion(batch_size=self.batch_size)
        if not rows:
            logging.info("[GRAPH] No entities ready for graph expansion. Sleeping...")
            return

        logging.info(f"[GRAPH] Starting batch expansion for {len(rows)} channels...")
        for row in rows:
            if self.shutdown_event.is_set():
                break

            await self.expand_entity(row)
            await asyncio.sleep(3)

    async def start(self):
        logging.info(f"Connecting to Redis at {self.redis_host}:{self.redis_port}...")
        self.redis_conn = redis.Redis(
            host=self.redis_host,
            port=self.redis_port,
            db=self.redis_db,
            password=self.redis_password,
            decode_responses=True
        )
        self.redis_conn.ping()

        logging.info(f"Connecting to PostgreSQL at {self.db_host}:{self.db_port}...")
        self.db_helper = DatabaseHelper(
            host=self.db_host,
            port=self.db_port,
            dbname=self.db_name,
            user=self.db_user,
            password=self.db_password
        )

        self.edge_mgr = GraphEdgeManager(db_conn=self.db_helper.conn, redis_conn=self.redis_conn)
        self.provenance_mgr = ProvenanceManager(redis_conn=self.redis_conn, db_conn=self.db_helper.conn)
        self.watermark_mgr = WatermarkManager(redis_conn=self.redis_conn, db_conn=self.db_helper.conn)
        self.importance_calc = GraphImportanceCalculator(db_conn=self.db_helper.conn)

        logging.info(f"Initializing Telegram Manager for session '{self.session_name}'...")
        self.tg_manager = TelegramManager(self.redis_conn, session_name=self.session_name, worker_type="graph_expander")
        await self.tg_manager.start_all()

        def stop():
            logging.info("[GRAPH] Shutdown signal received.")
            self.shutdown_event.set()

        loop = asyncio.get_running_loop()
        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, stop)
        except NotImplementedError:
            pass

        logging.info(f"[GRAPH] Multi-Edge Graph Expander Worker is active.")

        while not self.shutdown_event.is_set():
            try:
                await self.run_expansion_cycle()
            except Exception as e:
                logging.error(f"[GRAPH] Error in cycle: {e}", exc_info=True)

            try:
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=self.channel_interval)
            except asyncio.TimeoutError:
                pass

        await self.tg_manager.disconnect_all()
        self.db_helper.close()
        self.redis_conn.close()
        logging.info("[GRAPH] Graph expander stopped.")


if __name__ == "__main__":
    expander = GraphExpander()
    try:
        asyncio.run(expander.start())
    except KeyboardInterrupt:
        logging.info("[GRAPH] Stopped by user.")
    except Exception as e:
        logging.critical(f"[GRAPH] Fatal error: {e}")
        sys.exit(1)
