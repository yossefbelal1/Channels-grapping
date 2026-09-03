"""
app/scheduler/priority_scheduler.py — Dynamic Priority Crawl Scheduler
"""

import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class PriorityScheduler:
    """
    Schedules dynamic crawl and re-validation jobs based on channel priority and activity tier.
    """

    def __init__(self, redis_conn, db_conn=None):
        self.redis = redis_conn
        self.db = db_conn

    def get_channels_due_for_crawl(self, batch_size: int = 50) -> List[Dict[str, Any]]:
        """Finds active leads whose scheduled crawl time has arrived."""
        if not self.db:
            return []

        try:
            with self.db.cursor() as cur:
                cur.execute("""
                    SELECT id, channel_username, lead_score, tier, activity_class,
                           new_channel_score, member_count, next_crawl_at
                    FROM leads
                    WHERE status != 'rejected'
                      AND (next_crawl_at IS NULL OR next_crawl_at <= NOW())
                    ORDER BY
                        CASE WHEN activity_class = 'HOT' THEN 1
                             WHEN activity_class = 'WARM' THEN 2
                             WHEN activity_class = 'COLD' THEN 3
                             ELSE 4 END,
                        lead_score DESC NULLS LAST,
                        new_channel_score DESC NULLS LAST
                    LIMIT %s;
                """, (batch_size,))
                return [dict(r) for r in cur.fetchall()]
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
        """Pushes a crawl job into the appropriate Redis priority queue."""
        queue_name = "queue:normal"
        if priority == "critical" or activity_class == "HOT":
            queue_name = "queue:critical"
        elif priority == "high":
            queue_name = "queue:high"
        elif activity_class == "DORMANT":
            queue_name = "queue:low"

        payload = {
            "link": f"https://t.me/{channel_username}",
            "source": "priority_scheduler",
            "method": job_type,
            "channel_id": str(channel_id),
            "activity_class": activity_class,
            "scheduled_at": datetime.now(timezone.utc).isoformat()
        }

        try:
            self.redis.lpush(queue_name, json.dumps(payload))
            return True
        except Exception as err:
            logger.warning(f"Failed to enqueue crawl job for {channel_username}: {err}")
            return False
