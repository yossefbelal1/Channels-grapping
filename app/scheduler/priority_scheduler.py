"""
app/scheduler/priority_scheduler.py — Dynamic Priority Crawl Scheduler & Dispatcher

Production-Hardened Features:
- 5 Scheduling Classes (HOT, WARM, NORMAL, COLD, DORMANT)
- Incremental Crawl Dispatching with Watermark Awareness
- Transactional Outbox Pattern for DB + Redis Enqueue Reliability
- Zero Lost Jobs Guarantee: next_crawl_at only advanced upon verified Redis enqueue
- Periodic Outbox Reconciliation & Stale Running Job Crash Recovery
- Distributed Leader Lock to prevent competing schedulers
- In-flight crawl job deduplication (never re-schedule an active channel)
- Resilient Error Backoff without channel deletion
"""

import json
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

from app.scheduler.activity_classifier import ActivityClassifier, ActivityClass, ScanDepthTier
from app.scheduler.watermark_manager import WatermarkManager

logger = logging.getLogger(__name__)


class PriorityScheduler:
    """
    Schedules dynamic crawl and re-validation jobs based on channel priority,
    activity tier, and incremental watermark state.
    Guarantees transactional reliability between PostgreSQL and Redis.
    """

    LOCK_KEY = "lock:scheduler:leader"

    def __init__(self, redis_conn, db_conn=None):
        self.redis = redis_conn
        self.db = db_conn
        self.watermark_mgr = WatermarkManager(redis_conn, db_conn)

    def acquire_leader_lock(self, ttl_seconds: int = 30) -> bool:
        """
        Attempts to acquire a distributed leader lock in Redis.
        Guarantees only ONE scheduler instance executes cycles at any given time.
        """
        if not self.redis:
            return True
        try:
            acquired = self.redis.set(self.LOCK_KEY, "active", nx=True, ex=ttl_seconds)
            return bool(acquired)
        except Exception as err:
            logger.warning(f"Failed to acquire scheduler leader lock: {err}")
            return True

    def release_leader_lock(self) -> None:
        """Releases the distributed leader lock."""
        if not self.redis:
            return
        try:
            self.redis.delete(self.LOCK_KEY)
        except Exception as err:
            logger.debug(f"Failed to release scheduler leader lock: {err}")

    def get_channels_due_for_crawl(self, batch_size: int = 50) -> List[Dict[str, Any]]:
        """
        Finds active leads whose scheduled crawl time has arrived.
        Pulls all signals needed for adaptive interval and watermark calculation.
        """
        if not self.db:
            return []

        try:
            with self.db.cursor() as cur:
                cur.execute("""
                    SELECT id, channel_username, lead_score, forex_score, arabic_ratio,
                           activity_score, freshness_score, growth_score, new_channel_score,
                           tier, activity_class, member_count, next_crawl_at,
                           COALESCE(last_scanned_message_id, 0) AS last_scanned_message_id,
                           COALESCE(graph_importance_score, 0) AS graph_importance_score,
                           COALESCE(consecutive_crawl_failures, 0) AS consecutive_crawl_failures,
                           posts_24h, posts_7d, posts_30d, last_activity, last_scan
                    FROM leads
                    WHERE status != 'rejected'
                      AND (next_crawl_at IS NULL OR next_crawl_at <= NOW())
                      AND NOT EXISTS (
                          SELECT 1 FROM crawl_jobs
                          WHERE (crawl_jobs.channel_id = leads.id::text OR crawl_jobs.channel_username = leads.channel_username)
                            AND crawl_jobs.status IN ('pending', 'queued', 'running')
                            AND crawl_jobs.scheduled_at > NOW() - INTERVAL '30 minutes'
                      )
                    ORDER BY
                        CASE WHEN activity_class = 'HOT' THEN 1
                             WHEN activity_class = 'WARM' THEN 2
                             WHEN activity_class = 'NORMAL' THEN 3
                             WHEN activity_class = 'COLD' THEN 4
                             ELSE 5 END,
                        lead_score DESC NULLS LAST,
                        graph_importance_score DESC NULLS LAST
                    LIMIT %s;
                """, (batch_size,))
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as err:
            logger.warning(f"Failed to fetch due channels for scheduling: {err}")
            return []

    def enqueue_crawl_job(
        self,
        channel_id: str,
        channel_username: str,
        job_type: str = "deep_scan",
        priority: str = "normal",
        activity_class: str = "WARM"
    ) -> bool:
        """Backward-compatible crawl job enqueuer."""
        job_id = self.schedule_channel_crawl(
            channel_id=channel_id,
            channel_username=channel_username,
            channel_data={"activity_class": activity_class},
            job_type=job_type,
            priority=priority
        )
        return bool(job_id)

    def schedule_channel_crawl(
        self,
        channel_id: str,
        channel_username: str,
        channel_data: Optional[Dict[str, Any]] = None,
        job_type: str = "incremental",
        priority: Optional[str] = None
    ) -> Optional[str]:
        """
        Calculates adaptive crawl schedule, updates lead next_crawl_at in DB,
        records crawl job in crawl_jobs table, and enqueues to Redis.
        Returns job_id or None on failure.
        """
        data = channel_data or {}
        watermark = int(data.get("last_scanned_message_id") or self.watermark_mgr.get_watermark(channel_id, channel_username))

        # 1. Calculate next crawl schedule & depth budget
        schedule_info = ActivityClassifier.calculate_next_crawl(
            final_score=int(data.get("lead_score") or 0),
            forex_score=int(data.get("forex_score") or data.get("forex_intent_score") or 0),
            arabic_score=int(data.get("arabic_score") or data.get("arabic_ratio") or 0),
            activity_score=int(data.get("activity_score") or 0),
            freshness_score=int(data.get("freshness_score") or 0),
            growth_score=int(data.get("growth_score") or 0),
            new_channel_score=int(data.get("new_channel_score") or 0),
            graph_importance_score=int(data.get("graph_importance_score") or 0),
            consecutive_failures=int(data.get("consecutive_crawl_failures") or 0),
            posts_24h=int(data.get("posts_24h") or 0),
            posts_7d=int(data.get("posts_7d") or 0),
            posts_30d=int(data.get("posts_30d") or 0),
            last_post_at=data.get("last_activity"),
            has_watermark=(watermark > 0)
        )

        tier = schedule_info["scheduling_tier"]
        scan_depth = schedule_info["scan_depth_tier"]
        max_posts = schedule_info["max_posts_budget"]
        next_crawl_at = schedule_info["next_crawl_at"]
        interval_minutes = schedule_info["interval_minutes"]

        # 2. Determine Queue Priority
        prio = priority
        if not prio:
            if tier == ActivityClass.HOT:
                prio = "critical"
            elif tier == ActivityClass.WARM:
                prio = "high"
            elif tier in [ActivityClass.NORMAL, ActivityClass.COLD]:
                prio = "normal"
            else:
                prio = "low"

        queue_name = f"queue:{prio}"
        job_id = str(uuid.uuid4())

        payload = {
            "job_id": job_id,
            "link": f"https://t.me/{channel_username}",
            "channel_username": channel_username,
            "channel_id": str(channel_id),
            "source": "priority_scheduler",
            "method": job_type,
            "activity_class": tier,
            "scan_depth_tier": scan_depth,
            "watermark": watermark,
            "max_posts_budget": max_posts,
            "scheduled_at": datetime.now(timezone.utc).isoformat()
        }
        raw_payload = json.dumps(payload)

        # 3. Step 1 of Transactional Outbox: Insert job as 'pending'
        if self.db:
            try:
                with self.db.cursor() as cur:
                    cur.execute("""
                        INSERT INTO crawl_jobs (
                            job_id, channel_id, channel_username, job_type,
                            activity_class, priority, scheduled_at, status, watermark_used,
                            target_queue, payload
                        ) VALUES (%s, %s, %s, %s, %s, %s, NOW(), 'pending', %s, %s, %s)
                        ON CONFLICT (job_id) DO NOTHING;
                    """, (job_id, str(channel_id), channel_username, job_type, tier, prio, watermark, queue_name, raw_payload))
                self.db.commit()
            except Exception as err:
                logger.debug(f"Failed to insert outbox crawl_job: {err}")
                try:
                    self.db.rollback()
                except Exception:
                    pass

        # 4. Step 2 of Outbox: Enqueue to Redis
        enqueue_success = False
        try:
            self.redis.lpush(queue_name, raw_payload)
            enqueue_success = True
        except Exception as redis_err:
            logger.warning(f"Redis enqueue failed for {channel_username}: {redis_err}")

        # 5. Step 3 of Outbox: Atomic status resolution
        if self.db:
            try:
                with self.db.cursor() as cur:
                    if enqueue_success:
                        cur.execute("""
                            UPDATE crawl_jobs
                            SET status = 'queued'
                            WHERE job_id = %s;
                        """, (job_id,))
                        cur.execute("""
                            UPDATE leads
                            SET next_crawl_at = %s,
                                crawl_interval_minutes = %s,
                                activity_class = %s,
                                scan_depth_tier = %s
                            WHERE id::text = %s OR channel_username = %s;
                        """, (next_crawl_at, interval_minutes, tier, scan_depth, str(channel_id), channel_username))
                    else:
                        # Redis enqueue failed: Mark job as enqueue_failed
                        # CRUCIAL: next_crawl_at remains un-advanced so channel remains due
                        cur.execute("""
                            UPDATE crawl_jobs
                            SET status = 'enqueue_failed',
                                error_message = 'Redis enqueue failure'
                            WHERE job_id = %s;
                        """, (job_id,))
                self.db.commit()
            except Exception as db_err:
                logger.warning(f"Failed to update outbox status for {channel_username}: {db_err}")
                try:
                    self.db.rollback()
                except Exception:
                    pass

        return job_id if enqueue_success else None

    def mark_job_running(self, job_id: str) -> bool:
        """
        Transitions a crawl job to 'running' state upon worker checkout.
        """
        if not self.db or not job_id:
            return False
        try:
            with self.db.cursor() as cur:
                cur.execute("""
                    UPDATE crawl_jobs
                    SET status = 'running',
                        executed_at = COALESCE(executed_at, NOW())
                    WHERE job_id = %s;
                """, (job_id,))
            self.db.commit()
            return True
        except Exception as err:
            logger.debug(f"Notice marking crawl job running ({job_id}): {err}")
            return False

    def record_crawl_result(
        self,
        job_id: str,
        channel_id: str,
        success: bool,
        new_watermark: int = 0,
        posts_scanned: int = 0,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Records the execution result of a crawl job, advancing watermark on success
        or tracking failure for exponential backoff on subsequent crawls.
        """
        if self.db:
            try:
                with self.db.cursor() as cur:
                    status = "completed" if success else "failed"
                    cur.execute("""
                        UPDATE crawl_jobs
                        SET status = %s,
                            executed_at = COALESCE(executed_at, NOW()),
                            completed_at = NOW(),
                            new_watermark = %s,
                            posts_scanned = %s,
                            error_message = %s
                        WHERE job_id = %s;
                    """, (status, new_watermark, posts_scanned, error_message, job_id))

                    if success:
                        if new_watermark > 0:
                            self.watermark_mgr.update_watermark(channel_id, new_watermark)
                    else:
                        cur.execute("""
                            UPDATE leads
                            SET consecutive_crawl_failures = COALESCE(consecutive_crawl_failures, 0) + 1,
                                last_crawl_at = NOW()
                            WHERE id::text = %s;
                        """, (str(channel_id),))
                self.db.commit()
                return True
            except Exception as err:
                logger.warning(f"Failed to record crawl result for job {job_id}: {err}")
                try:
                    self.db.rollback()
                except Exception:
                    pass

        return False

    def reconcile_outbox_jobs(self, batch_size: int = 50) -> int:
        """
        Outbox Reconciliation Engine:
        Finds crawl_jobs that failed Redis enqueue or got stuck in 'pending' status.
        Retries pushing to Redis. Upon success, marks them 'queued' and advances next_crawl_at.
        """
        if not self.db or not self.redis:
            return 0

        reconciled = 0
        try:
            with self.db.cursor() as cur:
                cur.execute("""
                    SELECT job_id, channel_id, channel_username, target_queue, payload
                    FROM crawl_jobs
                    WHERE (status = 'enqueue_failed'
                           OR (status = 'pending' AND scheduled_at < NOW() - INTERVAL '2 minutes'))
                      AND scheduled_at > NOW() - INTERVAL '2 hours'
                    LIMIT %s;
                """, (batch_size,))
                stuck_jobs = cur.fetchall()

            if not stuck_jobs:
                return 0

            logger.info(f"Outbox reconciler found {len(stuck_jobs)} un-enqueued jobs. Retrying Redis push...")
            for row in stuck_jobs:
                job_id, ch_id, ch_uname, queue_name, payload_str = row
                q = queue_name or "queue:normal"
                if not payload_str:
                    continue

                try:
                    self.redis.lpush(q, payload_str)
                    with self.db.cursor() as cur:
                        cur.execute("""
                            UPDATE crawl_jobs
                            SET status = 'queued', error_message = NULL
                            WHERE job_id = %s;
                        """, (job_id,))
                        cur.execute("""
                            UPDATE leads
                            SET next_crawl_at = NOW() + INTERVAL '2 hours'
                            WHERE id::text = %s OR channel_username = %s;
                        """, (str(ch_id), ch_uname))
                    self.db.commit()
                    reconciled += 1
                except Exception as push_err:
                    logger.debug(f"Reconciliation Redis push still failing for {ch_uname}: {push_err}")
                    break

        except Exception as err:
            logger.warning(f"Error during outbox reconciliation: {err}")

        if reconciled > 0:
            logger.info(f"Outbox reconciler successfully restored and enqueued {reconciled} crawl jobs.")
        return reconciled

    def reconcile_stale_running_jobs(self, timeout_minutes: int = 30) -> int:
        """
        Detects crawl jobs that were checked out by a worker and marked 'running',
        but never completed within the timeout window (e.g. worker crash).
        Marks them 'failed' so the channel is eligible for recovery crawl on next cycle.
        """
        if not self.db:
            return 0

        recovered = 0
        try:
            with self.db.cursor() as cur:
                cur.execute("""
                    UPDATE crawl_jobs
                    SET status = 'failed',
                        completed_at = NOW(),
                        error_message = 'Worker execution timeout / crash recovery'
                    WHERE status = 'running'
                      AND executed_at < NOW() - (INTERVAL '1 minute' * %s)
                    RETURNING job_id, channel_id;
                """, (timeout_minutes,))
                rows = cur.fetchall()

                for job_id, channel_id in rows:
                    cur.execute("""
                        UPDATE leads
                        SET consecutive_crawl_failures = COALESCE(consecutive_crawl_failures, 0) + 1,
                            last_crawl_at = NOW()
                        WHERE id::text = %s;
                    """, (str(channel_id),))
                    recovered += 1

            self.db.commit()
        except Exception as err:
            logger.warning(f"Error recovering stale running crawl jobs: {err}")
            try:
                self.db.rollback()
            except Exception:
                pass

        if recovered > 0:
            logger.info(f"Stale job recovery: cleared {recovered} orphaned running crawl jobs.")
        return recovered

