"""
Unit tests for Activity Classifier & Priority Scheduler
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
from app.scheduler.activity_classifier import ActivityClassifier, ActivityClass
from app.scheduler.priority_scheduler import PriorityScheduler


def test_classify_hot_channel():
    act_class, interval, next_crawl = ActivityClassifier.classify_activity(
        posts_24h=8,
        posts_7d=45,
        posts_30d=150,
        last_post_at=datetime.now(timezone.utc)
    )
    assert act_class == ActivityClass.HOT
    assert interval == timedelta(hours=6)


def test_classify_dormant_channel():
    now = datetime.now(timezone.utc)
    old_post_date = now - timedelta(days=45)
    act_class, interval, next_crawl = ActivityClassifier.classify_activity(
        posts_24h=0,
        posts_7d=0,
        posts_30d=0,
        last_post_at=old_post_date
    )
    assert act_class == ActivityClass.DORMANT
    assert interval == timedelta(days=30)


def test_priority_scheduler_enqueue():
    mock_redis = MagicMock()
    scheduler = PriorityScheduler(redis_conn=mock_redis)

    ok = scheduler.enqueue_crawl_job(
        channel_id="11111111-1111-1111-1111-111111111111",
        channel_username="gold_trader_arab",
        job_type="deep_scan",
        priority="critical",
        activity_class="HOT"
    )

    assert ok is True
    assert mock_redis.lpush.called
    args = mock_redis.lpush.call_args[0]
    assert args[0] == "queue:critical" # Hot/Critical routes to critical queue
