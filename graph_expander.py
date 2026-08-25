"""
graph_expander.py — Worker D (The Graph Expander)

Continuously reads validated channels and groups from the database,
fetches 300–500 of their most recent posts, extracts all Telegram
links and @mentions, deduplicates against Redis, and pushes newly
discovered entities into the validator priority queues.

This creates the self-expanding graph discovery loop:
    DB Channels → Fetch 300–500 Posts → Extract Links
    → Push to queue:high with method="graph" → Validator → DB
    → More Channels → Repeat Forever

Safety features:
    - scan_cooldown:   channels are not re-expanded before their cooldown expires
    - max_depth:       configurable maximum graph traversal depth (default: 5)
    - seen_channels:   Redis set deduplication prevents re-queueing
    - adaptive jitter: TelegramManager enforces rate-limit safety delays
    - graceful shutdown: SIGINT/SIGTERM handled cleanly

Workers should run concurrently via docker-compose alongside:
    - scavenger.py  (keyword search)
    - radar.py      (live group listening)
    - validator.py  (validation + scoring)
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

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [GRAPH] [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# ── Regex (re-used from existing workers) ─────────────────────────────────────
TELEGRAM_LINK_REGEX = re.compile(
    r'(?:https?://)?(?:t\.me|telegram\.me)/(?:joinchat/)?\+?[a-zA-Z0-9_.-]+',
    re.IGNORECASE
)
USERNAME_REGEX = re.compile(r'@([a-zA-Z0-9_]{5,32})')

# ── Junk filter (same as radar.py / validator.py) ─────────────────────────────
JUNK_USERNAMES = {
    'joinchat', 'share', 'addstickers', 'addlist', 'gmail', 'hotmail',
    'yahoo', 'outlook', 'icloud', 'mail', 'yandex', 'protonmail', 'proton',
    'telegram', 'spambot', 'sticker', 'gif', 'bot', 'username', 'ads',
    'advertise', 'channel', 'group', 'chat', 'support', 'help', 'admin',
    'contact', 'info', 'service', 'feedback', 'terms', 'privacy'
}


class GraphExpander:
    """
    Deep post-crawling graph expansion engine.

    Reads validated channels/groups from the database, fetches their
    300–500 most recent posts, extracts Telegram links, and pushes
    new discoveries into the validation pipeline.
    """

    def __init__(self):
        load_dotenv()

        # ── Redis ──────────────────────────────────────────────────────────────
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.redis_db = int(os.getenv("REDIS_DB", 0))
        self.redis_password = os.getenv("REDIS_PASSWORD", None)

        # ── PostgreSQL ─────────────────────────────────────────────────────────
        self.db_host = os.getenv("DB_HOST", "localhost")
        self.db_port = int(os.getenv("DB_PORT", 5432))
        self.db_name = os.getenv("DB_NAME", "leadhunter_db")
        self.db_user = os.getenv("DB_USER", "postgres")
        self.db_password = os.getenv("DB_PASSWORD", "")

        # ── Configuration ──────────────────────────────────────────────────────
        self.session_name = os.getenv("SESSION_GRAPH_EXPANDER", "graph_expander_session")
        self.post_limit = int(os.getenv("GRAPH_EXPANDER_POST_LIMIT", 400))
        self.channel_interval = int(os.getenv("GRAPH_EXPANDER_INTERVAL_SECONDS", 600))  # 10 min between channels
        self.max_depth = int(os.getenv("GRAPH_MAX_DEPTH", 5))
        self.batch_size = int(os.getenv("GRAPH_EXPANDER_BATCH_SIZE", 15))  # channels per cycle

        # ── State ──────────────────────────────────────────────────────────────
        self.redis_conn = None
        self.db_helper = None
        self.tg_manager = None
        self.shutdown_event = asyncio.Event()

    # ── Database helpers ───────────────────────────────────────────────────────

    def get_channels_for_expansion(self, batch_size: int = 15, include_groups: bool = True) -> list:
        """
        Returns channels and groups that are ready for graph expansion.

        Selection criteria:
          - Not rejected or blacklisted
          - Not deeper than max_depth
          - Either never scanned by graph expander (last_graph_scan IS NULL)
            or their scan cooldown has expired based on score
        """
        self.db_helper.check_connection()

        # Separate channel and group queries to allow different cooldowns
        query = """
        SELECT
            channel_username,
            COALESCE(lead_score, 0) AS score,
            COALESCE(depth, 0) AS depth,
            is_group,
            last_graph_scan,
            COALESCE(marketplace_score, 0) AS marketplace_score
        FROM leads
        WHERE
            status NOT IN ('rejected')
            AND COALESCE(depth, 0) < %(max_depth)s
            AND (
                last_graph_scan IS NULL
                OR (
                    is_group = FALSE AND (
                        CASE
                            WHEN COALESCE(lead_score, 0) > 80 THEN last_graph_scan < NOW() - INTERVAL '3 days'
                            WHEN COALESCE(lead_score, 0) > 60 THEN last_graph_scan < NOW() - INTERVAL '7 days'
                            ELSE last_graph_scan < NOW() - INTERVAL '14 days'
                        END
                    )
                )
                OR (
                    is_group = TRUE AND (
                        CASE
                            WHEN COALESCE(marketplace_score, 0) > 60 THEN last_graph_scan < NOW() - INTERVAL '1 day'
                            WHEN COALESCE(marketplace_score, 0) > 30 THEN last_graph_scan < NOW() - INTERVAL '3 days'
                            ELSE last_graph_scan < NOW() - INTERVAL '7 days'
                        END
                    )
                )
            )
        ORDER BY
            CASE WHEN is_group = FALSE THEN COALESCE(lead_score, 0) ELSE COALESCE(marketplace_score, 0) END DESC,
            COALESCE(last_graph_scan, '2000-01-01') ASC
        LIMIT %(batch_size)s;
        """
        try:
            with self.db_helper.conn.cursor() as cur:
                cur.execute(query, {"max_depth": self.max_depth, "batch_size": batch_size})
                rows = cur.fetchall()
            logging.info(f"Graph expander found {len(rows)} entities ready for expansion.")
            return rows
        except Exception as e:
            logging.error(f"Error querying channels for expansion: {e}", exc_info=True)
            return []

    def update_last_graph_scan(self, channel_username: str):
        """Marks a channel as just scanned by the graph expander."""
        self.db_helper.check_connection()
        try:
            with self.db_helper.conn.cursor() as cur:
                cur.execute(
                    "UPDATE leads SET last_graph_scan = NOW() WHERE channel_username = %s",
                    (channel_username,)
                )
        except Exception as e:
            logging.error(f"Failed to update last_graph_scan for @{channel_username}: {e}")

    def insert_discovered_channel(self, username: str, source_username: str,
                                  depth: int, relation_type: str = 'graph_expansion'):
        """
        Creates a stub lead for the discovered channel with depth tracking,
        then inserts a graph edge from source → target.
        """
        self.db_helper.check_connection()
        try:
            # Upsert stub lead with depth (only sets depth if inserting new row)
            query = """
            INSERT INTO leads (channel_username, status, discovered_at, last_scan, depth, discovery_source, discovery_method)
            VALUES (%s, 'new', CURRENT_TIMESTAMP, NULL, %s, %s, 'graph')
            ON CONFLICT (channel_username)
            DO UPDATE SET
                discovery_source = COALESCE(leads.discovery_source, EXCLUDED.discovery_source),
                discovery_method = COALESCE(leads.discovery_method, EXCLUDED.discovery_method)
            RETURNING id;
            """
            with self.db_helper.conn.cursor() as cur:
                cur.execute(query, (username, depth, source_username))
                res = cur.fetchone()
                target_id = res['id'] if res else None

            if not target_id:
                target_id = self.db_helper.get_lead_id_by_username(username)

            # Insert graph edge
            source_id = self.db_helper.get_lead_id_by_username(source_username)
            if source_id and target_id and source_id != target_id:
                self.db_helper.insert_relationship(source_id, target_id, relation_type)

            return target_id
        except Exception as e:
            logging.error(f"Error inserting discovered channel @{username}: {e}")
            return None

    # ── Core expansion logic ───────────────────────────────────────────────────

    def check_backpressure(self, max_queued_threshold: int = 800) -> bool:
        """
        Checks if downstream validation queues are saturated.
        If saturated, pauses discovery production to prevent memory/queue bloat.
        """
        try:
            high_len = self.redis_conn.llen("queue:high")
            normal_len = self.redis_conn.llen("queue:normal")
            total = high_len + normal_len
            if total >= max_queued_threshold:
                logging.warning(
                    f"[GRAPH] 🛑 Queue Backpressure Active: {total} items queued ({high_len} high, {normal_len} normal). "
                    f"Throttling discovery..."
                )
                return True
        except Exception as e:
            logging.error(f"[GRAPH] Backpressure check error: {e}")
        return False

    async def fetch_posts(self, entity, limit: int = 400) -> list:
        """
        Fetches recent posts from a channel or group incrementally.
        Uses a message ID watermark to avoid re-downloading existing posts on every cycle.
        """
        username = getattr(entity, 'username', str(getattr(entity, 'id', 'unknown'))).lower()
        watermark_key = f"graph:watermark:{username}"
        last_max_id = self.redis_conn.get(watermark_key)

        min_id = int(last_max_id) if last_max_id and last_max_id.isdigit() else 0
        fetch_limit = min(150, limit) if min_id > 0 else limit

        async def fetch(cl):
            if min_id > 0:
                logging.info(f"[GRAPH] Incremental scan: fetching new posts since message ID {min_id} for @{username} (limit={fetch_limit})...")
                return await cl.get_messages(entity, limit=fetch_limit, min_id=min_id)
            else:
                logging.info(f"[GRAPH] Full initial scan: fetching up to {limit} posts for @{username}...")
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
            logging.error(f"Failed to fetch posts: {e}")
            return []

    async def get_entity_safe(self, username: str):
        """Resolves a Telegram username to an entity object."""
        async def resolve(cl):
            return await cl.get_entity(username)

        try:
            return await self.tg_manager.execute_request(
                self.session_name, resolve, shutdown_event=self.shutdown_event
            )
        except Exception as e:
            logging.warning(f"Could not resolve entity @{username}: {e}")
            return None

    def extract_links_from_messages(self, messages: list) -> dict:
        """
        Extracts and normalizes all Telegram links and @mentions
        from a list of messages.

        Returns: dict of {username_lower → (username, normalized_link, rel_type)}
        Deduplicates within the message batch.
        """
        discovered = {}

        for msg in messages:
            if not msg.text:
                continue

            text = msg.text

            # 1. Extract t.me / telegram.me links
            for raw_link in TELEGRAM_LINK_REGEX.findall(text):
                clean = raw_link.rstrip('.,;)!"\'')
                if not clean:
                    continue
                normalized = normalize_telegram_link(clean)
                link_type, target_username = parse_telegram_link(normalized)
                if link_type == 'public' and target_username:
                    key = target_username.lower()
                    if key not in discovered:
                        discovered[key] = (target_username, normalized, 'graph_link')

            # 2. Extract @mentions
            for mention in USERNAME_REGEX.findall(text):
                mention_lower = mention.lower()
                if mention_lower in JUNK_USERNAMES:
                    continue
                if mention_lower.endswith('bot') or mention_lower.endswith('_bot'):
                    continue
                if mention_lower not in discovered:
                    normalized = f"https://t.me/{mention}"
                    discovered[mention_lower] = (mention, normalized, 'graph_mention')

        return discovered

    async def expand_entity(self, row: dict) -> bool:
        """
        Performs graph expansion on a single channel or group:
          1. Resolve entity
          2. Fetch 300–500 posts
          3. Extract links
          4. Deduplicate against Redis seen_channels
          5. Push new discoveries to queue:high
          6. Create graph edges in DB
          7. Update last_scan timestamp
        """
        username = row['channel_username']
        parent_depth = int(row.get('depth') or 0)
        child_depth = parent_depth + 1
        is_group = row.get('is_group', False)

        entity_type = "group" if is_group else "channel"
        logging.info(
            f"[GRAPH] Expanding {entity_type} @{username} "
            f"(depth={parent_depth}, post_limit={self.post_limit})"
        )

        # Skip if max depth reached for children
        if child_depth > self.max_depth:
            logging.info(f"[GRAPH] Skipping @{username}: child depth {child_depth} exceeds max_depth {self.max_depth}")
            self.update_last_graph_scan(username)
            return False

        # Resolve entity
        entity = await self.get_entity_safe(username)
        if not entity:
            logging.warning(f"[GRAPH] Could not resolve @{username}. Marking as scanned and skipping.")
            self.update_last_graph_scan(username)
            return False

        # Fetch posts
        messages = await self.fetch_posts(entity, limit=self.post_limit)
        if not messages:
            logging.info(f"[GRAPH] No posts fetched from @{username}. Marking as scanned.")
            self.update_last_graph_scan(username)
            return False

        logging.info(f"[GRAPH] Fetched {len(messages)} posts from @{username}. Extracting links...")

        # Extract links from all posts
        discovered = self.extract_links_from_messages(messages)
        logging.info(f"[GRAPH] Found {len(discovered)} unique links/mentions in @{username}")

        new_discoveries = 0
        for target_lower, (target_username, normalized_link, rel_type) in discovered.items():
            if self.shutdown_event.is_set():
                break

            # Skip self-references
            if target_lower == username.lower():
                continue

            # Check blacklist
            if self.db_helper.is_blacklisted(normalized_link):
                continue

            # Check Redis deduplication
            is_seen = self.redis_conn.sismember("seen_channels", normalized_link)

            # Always create graph edge regardless of seen status
            self.insert_discovered_channel(
                username=target_username,
                source_username=username,
                depth=child_depth,
                relation_type=rel_type
            )

            if not is_seen:
                # Mark as seen to prevent duplicates across workers
                self.redis_conn.sadd("seen_channels", normalized_link)

                # Route to queue:high (graph discoveries are high-value)
                payload = json.dumps({
                    "link": normalized_link,
                    "source": username,
                    "method": "graph",
                    "keyword": "",
                    "depth": child_depth
                })
                self.redis_conn.rpush("queue:high", payload)
                new_discoveries += 1
                logging.info(
                    f"[GRAPH] New discovery: {normalized_link} "
                    f"(source=@{username}, depth={child_depth}, rel={rel_type})"
                )

        logging.info(
            f"[GRAPH] @{username} expansion complete: "
            f"{len(messages)} posts → {len(discovered)} unique links → "
            f"{new_discoveries} new queued for validation."
        )

        # Update last_graph_scan so this channel won't be re-expanded too soon
        self.update_last_graph_scan(username)
        return True

    # ── Main loop ──────────────────────────────────────────────────────────────

    async def run_expansion_cycle(self):
        """
        Runs a single batch expansion cycle:
          1. Pull batch of channels/groups from DB
          2. For each: expand (fetch posts, extract links, queue new ones)
          3. Sleep between channels to respect Telegram rate limits
        """
        rows = self.get_channels_for_expansion(batch_size=self.batch_size)

        if not rows:
            logging.info("[GRAPH] No channels ready for expansion. Sleeping until next cycle.")
            return

        logging.info(f"[GRAPH] Starting expansion cycle: {len(rows)} entities to process.")

        for row in rows:
            if self.shutdown_event.is_set():
                break

            # Backpressure throttle: wait if downstream queues are backed up
            while self.check_backpressure(max_queued_threshold=800) and not self.shutdown_event.is_set():
                try:
                    await asyncio.wait_for(self.shutdown_event.wait(), timeout=30)
                except asyncio.TimeoutError:
                    pass

            if self.shutdown_event.is_set():
                break

            was_expanded = await self.expand_entity(row)

            # Respect Telegram rate limits between channels
            if not self.shutdown_event.is_set():
                if not was_expanded:
                    sleep_seconds = 5
                    logging.info(f"[GRAPH] Channel skipped/failed. Sleeping {sleep_seconds}s before next entity.")
                else:
                    health = self.tg_manager.get_health_score(self.session_name)

                    if health >= 80:
                        sleep_seconds = self.channel_interval          # normal delay
                    elif health >= 50:
                        sleep_seconds = self.channel_interval * 2      # 2x delay
                    elif health >= 30:
                        sleep_seconds = self.channel_interval * 4      # 4x delay (cooldown)
                    else:
                        sleep_seconds = self.channel_interval * 8      # 8x delay (heavy restriction)
                        logging.warning(
                            f"[GRAPH] Account health is critically low ({health}). "
                            f"Sleeping {sleep_seconds}s to recover..."
                        )

                    logging.info(
                        f"[GRAPH] Sleeping {sleep_seconds}s before next channel "
                        f"(account health: {health})..."
                    )
                try:
                    await asyncio.wait_for(self.shutdown_event.wait(), timeout=sleep_seconds)
                except asyncio.TimeoutError:
                    pass

        logging.info("[GRAPH] Expansion cycle complete.")

    async def start(self):
        """
        Main entry point. Initializes connections and runs the continuous
        graph expansion loop indefinitely until shutdown.
        """
        # ── Redis ──────────────────────────────────────────────────────────────
        logging.info(f"Connecting to Redis at {self.redis_host}:{self.redis_port}...")
        try:
            self.redis_conn = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                password=self.redis_password,
                decode_responses=True
            )
            self.redis_conn.ping()
            logging.info("Redis connection established.")
        except Exception as e:
            logging.error(f"Failed to connect to Redis: {e}")
            sys.exit(1)

        # ── PostgreSQL ─────────────────────────────────────────────────────────
        logging.info(f"Connecting to PostgreSQL at {self.db_host}:{self.db_port}...")
        try:
            self.db_helper = DatabaseHelper(
                host=self.db_host,
                port=self.db_port,
                dbname=self.db_name,
                user=self.db_user,
                password=self.db_password
            )
            logging.info("PostgreSQL connection established.")
        except Exception as e:
            logging.error(f"Failed to connect to PostgreSQL: {e}")
            sys.exit(1)

        # ── Telegram Manager ───────────────────────────────────────────────────
        logging.info(f"Initializing Telegram Manager for session: {self.session_name}...")
        self.tg_manager = TelegramManager(self.redis_conn, session_name=self.session_name)
        await self.tg_manager.start_all()

        # ── Signal Handlers ────────────────────────────────────────────────────
        def trigger_shutdown():
            logging.info("[GRAPH] Shutdown signal received. Finishing current task then stopping...")
            self.shutdown_event.set()

        loop = asyncio.get_running_loop()
        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, trigger_shutdown)
        except NotImplementedError:
            pass  # Windows — signal handlers not supported in asyncio

        logging.info(
            f"[GRAPH] Worker D (The Graph Expander) is active.\n"
            f"  Session:    {self.session_name}\n"
            f"  Post limit: {self.post_limit} posts per channel\n"
            f"  Interval:   {self.channel_interval}s between channels\n"
            f"  Max depth:  {self.max_depth}\n"
            f"  Batch size: {self.batch_size} channels per cycle"
        )

        # ── Main Loop ──────────────────────────────────────────────────────────
        # Inter-cycle sleep: after processing a full batch, wait before starting next batch.
        # This ensures continuous but non-abusive expansion.
        inter_cycle_sleep = int(os.getenv("GRAPH_EXPANDER_CYCLE_SLEEP", 3600))  # Default: 1 hour between cycles

        while not self.shutdown_event.is_set():
            try:
                await self.run_expansion_cycle()
            except Exception as e:
                logging.error(f"[GRAPH] Error in expansion cycle: {e}", exc_info=True)

            if not self.shutdown_event.is_set():
                logging.info(
                    f"[GRAPH] Cycle finished. Sleeping {inter_cycle_sleep}s before next cycle..."
                )
                try:
                    await asyncio.wait_for(self.shutdown_event.wait(), timeout=inter_cycle_sleep)
                except asyncio.TimeoutError:
                    pass

        # ── Cleanup ────────────────────────────────────────────────────────────
        await self.tg_manager.disconnect_all()
        self.db_helper.close()
        self.redis_conn.close()
        logging.info("[GRAPH] Worker D (The Graph Expander) has stopped.")


if __name__ == "__main__":
    expander = GraphExpander()
    try:
        asyncio.run(expander.start())
    except KeyboardInterrupt:
        logging.info("[GRAPH] Process interrupted by user. Exiting.")
    except Exception as e:
        logging.critical(f"[GRAPH] FATAL WORKER ERROR: {e}", exc_info=True)
        sys.exit(1)
