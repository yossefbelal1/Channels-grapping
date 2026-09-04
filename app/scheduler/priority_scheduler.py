"""
app/scheduler/priority_scheduler.py — Dynamic Priority Crawl Scheduler & Dispatcher

Production-Hardened Features:
- 5 Scheduling Classes (HOT, WARM, NORMAL, COLD, DORMANT)
- Incremental Crawl Dispatching with Watermark Awareness
- Tiered Scan Depth propagation to Worker Queues
- Persistent Crawl Job Audit Trail in PostgreSQL crawl_jobs table
- Resilient Error Backoff without channel deletion
"""

import json
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from app.scheduler.activity_classifier import ActivityClassifier, ActivityClass, ScanDepthTier
from app.scheduler.watermark_manager import WatermarkManager

logger = logging.getLogger(__name__)


class PriorityScheduler:
    """
    Schedules dynamic crawl and re-validation jobs based on channel priority,
    activity tier, and incremental watermark state.
    """

    def __init__(self, redis_conn, db_conn=None):
        self.redis = redis_conn
        self.db = db_conn
        self.watermark_mgr = WatermarkManager(redis_conn, db_conn)

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
            forex_score=int(data.get("forex_score") or 0),
            arabic_score=int(data.get("arabic_ratio") or 0),
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

        # 2. Update PostgreSQL leads next_crawl_at and interval
        if self.db:
            try:
                with self.db.cursor() as cur:
                    cur.execute("""
                        UPDATE leads
                        SET next_crawl_at = %s,
                            crawl_interval_minutes = %s,
                            activity_class = %s,
                            scan_depth_tier = %s
                        WHERE id::text = %s OR channel_username = %s;
                    """, (next_crawl_at, interval_minutes, tier, scan_depth, str(channel_id), channel_username))
                self.db.commit()
            except Exception as err:
                logger.warning(f"Failed to update next_crawl_at for {channel_username}: {err}")
                try:
                    self.db.rollback()
                except Exception:
                    pass

        # 3. Determine Queue Priority
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

        # 4. Insert into crawl_jobs table
        if self.db:
            try:
                with self.db.cursor() as cur:
                    cur.execute("""
                        INSERT INTO crawl_jobs (
                            job_id, channel_id, channel_username, job_type,
                            activity_class, priority, scheduled_at, status, watermark_used
                        ) VALUES (%s, %s, %s, %s, %s, %s, NOW(), 'pending', %s)
                        ON CONFLICT (job_id) DO NOTHING;
                    """, (job_id, str(channel_id), channel_username, job_type, tier, prio, watermark))
                self.db.commit()
            except Exception as err:
                logger.debug(f"Failed to insert crawl_job row: {err}")
                try:
                    self.db.rollback()
                except Exception:
                    pass

        # 5. Push to Redis queue
        try:
            self.redis.lpush(queue_name, json.dumps(payload))
            return job_id
        except Exception as err:
            logger.warning(f"Failed to enqueue crawl job for {channel_username}: {err}")
            return None

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
