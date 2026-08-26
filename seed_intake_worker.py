"""
seed_intake_worker.py — Seed Channel Intake Worker

Bridges external systems (AutoTele, manual seeds, web scrapers) with the
Channels-grapping discovery pipeline.

External systems INSERT rows into the `seed_channels` table.
This worker polls the table every 60 seconds, pushes unprocessed seeds into
the `queue:high` Redis validation queue, and marks them as processed.

AutoTele Integration:
    AutoTele simply executes:
        INSERT INTO seed_channels (channel_username, source, notes)
        VALUES ('SomeForexChannel', 'autotele', 'Seen in promoted post')
        ON CONFLICT (channel_username) DO NOTHING;

    This worker picks it up within 60 seconds and routes it to the validator.

Other External Systems:
    Any system with database access can INSERT into seed_channels.
    The `source` field identifies which system provided the seed.

Queue routing:
    - Seeds from AutoTele → queue:high (high-value, pre-filtered)
    - Seeds from other sources → queue:normal

Safety:
    - Duplicate seeds are ignored (UNIQUE constraint on channel_username)
    - Seeds are marked processed BEFORE queuing to prevent duplicate queuing
      if the worker restarts mid-cycle
    - Graceful SIGINT/SIGTERM handling
"""

import os
import sys
import json
import asyncio
import signal
import logging
from dotenv import load_dotenv
import redis
import psycopg2
from psycopg2.extras import RealDictCursor
from app.core.db import get_db_connection

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [SEED] [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

LUA_ATOMIC_SEED_ENQUEUE = """
local is_seen = redis.call("SISMEMBER", KEYS[1], ARGV[1])
if is_seen == 1 then
    return 0
end
redis.call("SADD", KEYS[1], ARGV[1])
redis.call("RPUSH", KEYS[2], ARGV[2])
return 1
"""


class SeedIntakeWorker:
    """
    Polls the seed_channels table and feeds new seeds into the
    validation priority queues.
    """

    # Sources that receive elevated queue priority
    HIGH_PRIORITY_SOURCES = {'autotele', 'graph', 'manual'}

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
        self.poll_interval = int(os.getenv("SEED_INTAKE_POLL_SECONDS", 60))
        self.batch_size = int(os.getenv("SEED_INTAKE_BATCH_SIZE", 50))

        # ── State ──────────────────────────────────────────────────────────────
        self.redis_conn = None
        self.db_conn = None
        self.shutdown_event = asyncio.Event()

    # ── Database connection ────────────────────────────────────────────────────

    def connect_db(self):
        """Acquires a pooled PostgreSQL connection."""
        try:
            self.db_conn = get_db_connection()
            logging.info("PostgreSQL pooled connection established.")
        except Exception as e:
            logging.error(f"Failed to acquire PostgreSQL connection: {e}")
            raise

    def check_db_connection(self):
        """Reconnects if connection is lost."""
        if self.db_conn is None or self.db_conn.closed:
            logging.warning("DB connection closed. Reconnecting...")
            self.connect_db()

    # ── Core polling logic ─────────────────────────────────────────────────────

    def fetch_unprocessed_seeds(self) -> list:
        """
        Fetches a batch of unprocessed seeds from the seed_channels table.
        Orders by created_at ASC (oldest seeds first — FIFO).
        """
        self.check_db_connection()
        query = """
        SELECT id, channel_username, source, notes, created_at
        FROM seed_channels
        WHERE processed = FALSE
        ORDER BY created_at ASC
        LIMIT %s;
        """
        try:
            with self.db_conn.cursor() as cur:
                cur.execute(query, (self.batch_size,))
                return cur.fetchall()
        except Exception as e:
            logging.error(f"Error fetching seeds: {e}", exc_info=True)
            return []

    def mark_seed_processed(self, seed_id: str):
        """Marks a single seed as processed with current timestamp."""
        self.check_db_connection()
        try:
            with self.db_conn.cursor() as cur:
                cur.execute(
                    "UPDATE seed_channels SET processed = TRUE, processed_at = NOW() WHERE id = %s",
                    (seed_id,)
                )
        except Exception as e:
            logging.error(f"Failed to mark seed {seed_id} as processed: {e}")

    def process_seeds(self, seeds: list) -> tuple:
        """
        Processes a batch of seeds atomically:
          - Uses Redis Lua script to atomically check deduplication and push to queue.
          - If Redis push fails, the seed remains pending in DB and is NOT marked as seen.
          - Marks seed as processed in PostgreSQL ONLY after confirmed Redis enqueue or if already known.
          - Returns (queued_count, skipped_count)
        """
        queued = 0
        skipped = 0

        for seed in seeds:
            seed_id = str(seed['id'])
            username = seed['channel_username'].strip().lstrip('@')
            source = seed.get('source') or 'unknown'
            notes = seed.get('notes') or ''

            if not username:
                self.mark_seed_processed(seed_id)
                continue

            # Normalize to standard link format
            normalized_link = f"https://t.me/{username}"

            # Determine priority queue based on source
            if source.lower() in self.HIGH_PRIORITY_SOURCES:
                queue_target = "queue:high"
            else:
                queue_target = "queue:normal"

            # Build payload compatible with validator.py's process_link()
            payload = json.dumps({
                "link": normalized_link,
                "source": source,
                "method": "seed",
                "keyword": "",
                "notes": notes
            })

            try:
                # Atomic check-and-enqueue via Redis Lua script
                res = self.redis_conn.eval(
                    LUA_ATOMIC_SEED_ENQUEUE, 2, "seen_channels", queue_target, normalized_link, payload
                )
                if res == 1:
                    self.mark_seed_processed(seed_id)
                    queued += 1
                    logging.info(
                        f"[SEED] Queued @{username} → {queue_target} "
                        f"(source={source}, id={seed_id[:8]}...)"
                    )
                elif res == 0:
                    self.mark_seed_processed(seed_id)
                    skipped += 1
                    logging.info(f"[SEED] Already known: @{username} (source={source}). Marked processed & skipped.")
            except Exception as enqueue_err:
                logging.error(f"[SEED] Failed atomic enqueue for @{username}: {enqueue_err}. Will retry on next cycle.")

        return queued, skipped

    # ── Main loop ──────────────────────────────────────────────────────────────

    async def run_poll_cycle(self):
        """
        Runs one poll cycle:
          1. Fetch unprocessed seeds
          2. Process and queue them
          3. Log summary
        """
        seeds = self.fetch_unprocessed_seeds()

        if not seeds:
            logging.debug(f"[SEED] No new seeds. Will check again in {self.poll_interval}s.")
            return

        logging.info(f"[SEED] Found {len(seeds)} unprocessed seed(s). Processing...")
        queued, skipped = self.process_seeds(seeds)
        logging.info(
            f"[SEED] Cycle complete: {queued} queued for validation, {skipped} skipped (already known)."
        )

    async def start(self):
        """
        Main entry point. Connects to Redis and PostgreSQL, then runs
        the polling loop indefinitely until shutdown.
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
            self.connect_db()
        except Exception as e:
            logging.error(f"Failed to connect to PostgreSQL: {e}")
            sys.exit(1)

        # ── Signal Handlers ────────────────────────────────────────────────────
        def trigger_shutdown():
            logging.info("[SEED] Shutdown signal received. Stopping gracefully...")
            self.shutdown_event.set()

        loop = asyncio.get_running_loop()
        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, trigger_shutdown)
        except NotImplementedError:
            pass  # Windows

        logging.info(
            f"[SEED] Seed Intake Worker is active.\n"
            f"  Poll interval: {self.poll_interval}s\n"
            f"  Batch size:    {self.batch_size} seeds per cycle\n"
            f"  High-priority sources: {self.HIGH_PRIORITY_SOURCES}"
        )

        # ── Main Poll Loop ─────────────────────────────────────────────────────
        while not self.shutdown_event.is_set():
            try:
                await self.run_poll_cycle()
            except Exception as e:
                logging.error(f"[SEED] Error in poll cycle: {e}", exc_info=True)

            # Wait for next poll interval (or shutdown signal)
            try:
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=self.poll_interval)
            except asyncio.TimeoutError:
                pass

        # ── Cleanup ────────────────────────────────────────────────────────────
        if self.db_conn and not self.db_conn.closed:
            self.db_conn.close()
        if self.redis_conn:
            self.redis_conn.close()
        logging.info("[SEED] Seed Intake Worker has stopped.")


# ── AutoTele Integration Helper ───────────────────────────────────────────────
# For reference: AutoTele can call this SQL to submit seeds:
#
#   INSERT INTO seed_channels (channel_username, source, notes)
#   VALUES (%s, 'autotele', %s)
#   ON CONFLICT (channel_username) DO NOTHING;
#
# Or to batch-insert multiple seeds:
#
#   INSERT INTO seed_channels (channel_username, source, notes)
#   VALUES
#     ('ForexChannel1', 'autotele', 'Promoted in group X'),
#     ('GoldSignals99', 'autotele', 'Found via promoted post'),
#     ...
#   ON CONFLICT (channel_username) DO NOTHING;
#
# The seed_intake_worker.py will process them within SEED_INTAKE_POLL_SECONDS.
# ─────────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    worker = SeedIntakeWorker()
    try:
        asyncio.run(worker.start())
    except KeyboardInterrupt:
        logging.info("[SEED] Process interrupted by user. Exiting.")
    except Exception as e:
        logging.critical(f"[SEED] FATAL WORKER ERROR: {e}", exc_info=True)
        sys.exit(1)
