"""
scheduler_worker.py — Autonomous Production Crawl Scheduler Daemon (Worker S)

Responsibilities:
1. Polls PostgreSQL for due channels using PriorityScheduler
2. Respects system backpressure (slows down or pauses when validation/Redis is saturated)
3. Evaluates 5 dynamic scheduling tiers (HOT, WARM, NORMAL, COLD, DORMANT)
4. Enqueues crawl jobs with incremental watermarks and scan depth budgets
5. Persists next_crawl_at, interval, and audit trail in crawl_jobs table
6. Recovers cleanly after restarts and handles SIGINT/SIGTERM gracefully
"""

import os
import sys
import time
import json
import signal
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
import redis

from validator import DatabaseHelper
from app.scheduler.priority_scheduler import PriorityScheduler
from app.outreach.backpressure import BackpressureManager, BackpressureLevel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [SCHEDULER] [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("scheduler_worker")


class SchedulerWorker:
    """
    Dedicated production worker driving the continuous, dynamic crawl loop.
    """

    def __init__(
        self,
        redis_host: Optional[str] = None,
        redis_port: Optional[int] = None,
        redis_db: Optional[int] = None,
        redis_password: Optional[str] = None,
        db_host: Optional[str] = None,
        db_port: Optional[int] = None,
        db_name: Optional[str] = None,
        db_user: Optional[str] = None,
        db_password: Optional[str] = None,
        batch_size: Optional[int] = None,
        poll_interval: Optional[int] = None,
    ):
        load_dotenv()

        self.redis_host = redis_host or os.getenv("REDIS_HOST", "localhost")
        self.redis_port = redis_port or int(os.getenv("REDIS_PORT", 6379))
        self.redis_db = redis_db if redis_db is not None else int(os.getenv("REDIS_DB", 0))
        self.redis_password = redis_password or os.getenv("REDIS_PASSWORD", None)

        self.db_host = db_host or os.getenv("DB_HOST", "localhost")
        self.db_port = db_port or int(os.getenv("DB_PORT", 5432))
        self.db_name = db_name or os.getenv("DB_NAME", "leadhunter_db")
        self.db_user = db_user or os.getenv("DB_USER", "postgres")
        self.db_password = db_password or os.getenv("DB_PASSWORD", "")

        self.batch_size = batch_size or int(os.getenv("SCHEDULER_BATCH_SIZE", "50"))
        self.poll_interval = poll_interval or int(os.getenv("SCHEDULER_POLL_INTERVAL_SECONDS", "30"))

        self.redis_conn = None
        self.db_helper = None
        self.scheduler = None
        self.backpressure_mgr = None
        self.shutdown_event = asyncio.Event()
        self.cycle_count = 0

    def connect(self):
        logger.info(f"Connecting to Redis at {self.redis_host}:{self.redis_port}...")
        self.redis_conn = redis.Redis(
            host=self.redis_host,
            port=self.redis_port,
            db=self.redis_db,
            password=self.redis_password,
            decode_responses=True
        )
        self.redis_conn.ping()

        logger.info(f"Connecting to PostgreSQL at {self.db_host}:{self.db_port}/{self.db_name}...")
        self.db_helper = DatabaseHelper(
            host=self.db_host,
            port=self.db_port,
            dbname=self.db_name,
            user=self.db_user,
            password=self.db_password
        )

        # Run database migrations safely if needed
        self._apply_migrations_if_needed()

        self.scheduler = PriorityScheduler(redis_conn=self.redis_conn, db_conn=self.db_helper.conn)
        self.backpressure_mgr = BackpressureManager(self.redis_conn)
        logger.info("Scheduler Worker initialized successfully.")

    def _apply_migrations_if_needed(self):
        """Ensures v7 schema changes are present in the target database."""
        for mig_file in ['migrate_v6_channel_intelligence.sql', 'migrate_v7_production_hardening.sql']:
            mig_path = os.path.join(os.path.dirname(__file__), mig_file)
            if os.path.exists(mig_path):
                try:
                    with open(mig_path, 'r', encoding='utf-8') as f:
                        sql = f.read()
                    with self.db_helper.conn.cursor() as cur:
                        cur.execute(sql)
                    self.db_helper.conn.commit()
                    logger.info(f"Verified / applied migration: {mig_file}")
                except Exception as err:
                    logger.warning(f"Migration check for {mig_file} (may already be applied): {err}")
                    try:
                        self.db_helper.conn.rollback()
                    except Exception:
                        pass

    async def run_schedule_cycle(self) -> int:
        """
        Executes one complete scheduling cycle:
        1. Acquires distributed leader lock to prevent competing schedulers
        2. Emits Redis heartbeat for monitoring
        3. Reconciles any un-enqueued outbox jobs and stale running jobs
        4. Evaluates backpressure
        5. Queries due channels from PostgreSQL
        6. Dynamically calculates interval, tier, depth, and watermark
        7. Enqueues crawl jobs into Redis priority queues
        """
        # 1. Acquire distributed leader lock
        lock_acquired = self.scheduler.acquire_leader_lock(ttl_seconds=45)
        if not lock_acquired:
            logger.info("Another scheduler holds the leader lock. Skipping cycle.")
            return 0

        try:
            self.cycle_count += 1

            # 2. Update Heartbeat in Redis
            if self.redis_conn:
                try:
                    self.redis_conn.setex(
                        "heartbeat:worker:scheduler",
                        60,
                        datetime.now(timezone.utc).isoformat()
                    )
                except Exception as hb_err:
                    logger.debug(f"Heartbeat update warning: {hb_err}")

            # 3. Run Outbox Reconciliation & Stale Job Recovery
            try:
                self.scheduler.reconcile_outbox_jobs(batch_size=20)
                if self.cycle_count % 10 == 0:
                    self.scheduler.reconcile_stale_running_jobs(timeout_minutes=30)
            except Exception as rec_err:
                logger.warning(f"Reconciliation cycle warning: {rec_err}")

            # 4. Check Backpressure
            pressure = self.backpressure_mgr.get_composite_pressure()
            if pressure == BackpressureLevel.CRITICAL:
                logger.warning("System backpressure CRITICAL (downstream queues saturated). Pausing crawl scheduling...")
                return 0

            concurrency_factor = self.backpressure_mgr.recommended_concurrency_factor()
            effective_batch = max(5, int(self.batch_size * concurrency_factor))

            # 5. Fetch due channels
            self.db_helper.check_connection()
            due_channels = self.scheduler.get_channels_due_for_crawl(batch_size=effective_batch)
            if not due_channels:
                logger.debug("No channels currently due for crawl.")
                return 0

            logger.info(f"Found {len(due_channels)} channels due for scheduled crawl. Dispatching jobs...")
            enqueued_count = 0

            # 6. Schedule and dispatch each due channel
            for ch in due_channels:
                if self.shutdown_event.is_set():
                    break

                channel_id = str(ch.get("id"))
                username = ch.get("channel_username")
                if not username:
                    continue

                job_id = self.scheduler.schedule_channel_crawl(
                    channel_id=channel_id,
                    channel_username=username,
                    channel_data=ch,
                    job_type="incremental" if ch.get("last_scanned_message_id", 0) > 0 else "deep_scan"
                )

                if job_id:
                    enqueued_count += 1

            logger.info(f"Crawl scheduling cycle complete: {enqueued_count}/{len(due_channels)} jobs dispatched.")
            return enqueued_count

        finally:
            self.scheduler.release_leader_lock()


    async def start(self):
        self.connect()

        loop = asyncio.get_running_loop()
        def on_shutdown():
            logger.info("Shutdown signal received. Stopping Scheduler Worker gracefully...")
            self.shutdown_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, on_shutdown)
            except NotImplementedError:
                pass

        logger.info(f"Scheduler Worker running. Polling every {self.poll_interval}s...")
        while not self.shutdown_event.is_set():
            try:
                await self.run_schedule_cycle()
            except Exception as err:
                logger.error(f"Error in scheduler worker cycle: {err}", exc_info=True)

            try:
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=self.poll_interval)
            except asyncio.TimeoutError:
                pass

        logger.info("Scheduler Worker stopped.")


if __name__ == "__main__":
    worker = SchedulerWorker()
    asyncio.run(worker.start())
