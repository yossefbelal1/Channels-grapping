"""
tests/test_priority_scheduler_hardened.py — Test Suite for v7 Dynamic Crawl Scheduler & Watermarks
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from app.scheduler.activity_classifier import (
    ActivityClassifier,
    ActivityClass,
    ScanDepthTier
)
from app.scheduler.watermark_manager import WatermarkManager
from app.scheduler.priority_scheduler import PriorityScheduler


def test_activity_classifier_5_tiers():
    assert ActivityClass.HOT == "HOT"
    assert ActivityClass.WARM == "WARM"
    assert ActivityClass.NORMAL == "NORMAL"
    assert ActivityClass.COLD == "COLD"
    assert ActivityClass.DORMANT == "DORMANT"


def test_calculate_next_crawl_hot_channel():
    now = datetime.now(timezone.utc)
    res = ActivityClassifier.calculate_next_crawl(
        final_score=85,
        forex_score=90,
        arabic_score=80,
        posts_24h=10,
        posts_7d=50,
        last_post_at=now - timedelta(hours=1),
        has_watermark=False
    )
    assert res["scheduling_tier"] == ActivityClass.HOT
    assert res["scan_depth_tier"] == ScanDepthTier.DEEP
    assert res["interval_minutes"] <= 360 # <= 6 hours
    assert res["next_crawl_at"] > now


def test_calculate_next_crawl_dormant_never_rejected():
    now = datetime.now(timezone.utc)
    res = ActivityClassifier.calculate_next_crawl(
        final_score=60,
        forex_score=70,
        arabic_score=65,
        posts_24h=0,
        posts_7d=0,
        posts_30d=0,
        last_post_at=now - timedelta(days=45), # inactive 45 days
        has_watermark=False
    )
    # Must be classified as DORMANT with long interval, NEVER rejected
    assert res["scheduling_tier"] == ActivityClass.DORMANT
    assert res["scan_depth_tier"] == ScanDepthTier.LIGHT
    assert res["interval_minutes"] >= 14400 # Multi-day interval (<=30 days)
    assert res["next_crawl_at"] > now


def test_calculate_next_crawl_with_watermark_incremental():
    now = datetime.now(timezone.utc)
    res = ActivityClassifier.calculate_next_crawl(
        final_score=75,
        forex_score=60,
        posts_24h=2,
        posts_7d=14,
        has_watermark=True
    )
    assert res["scan_depth_tier"] == ScanDepthTier.INCREMENTAL
    assert res["max_posts_budget"] == 100


def test_calculate_next_crawl_consecutive_failures_backoff():
    now = datetime.now(timezone.utc)
    normal_res = ActivityClassifier.calculate_next_crawl(
        final_score=50,
        posts_7d=5,
        consecutive_failures=0
    )
    failed_res = ActivityClassifier.calculate_next_crawl(
        final_score=50,
        posts_7d=5,
        consecutive_failures=3
    )
    # Failures must increase interval
    assert failed_res["interval_minutes"] > normal_res["interval_minutes"]


def test_watermark_manager_redis_cache():
    mock_redis = MagicMock()
    mock_redis.get.return_value = "10452"

    mgr = WatermarkManager(redis_conn=mock_redis, db_conn=None)
    wm = mgr.get_watermark("ch_123")
    assert wm == 10452
    mock_redis.get.assert_called_with("watermark:channel:ch_123")


def test_priority_scheduler_enqueue():
    mock_redis = MagicMock()
    scheduler = PriorityScheduler(redis_conn=mock_redis, db_conn=None)

    channel_data = {
        "lead_score": 80,
        "forex_score": 75,
        "posts_24h": 8,
        "last_scanned_message_id": 500
    }
    job_id = scheduler.schedule_channel_crawl(
        channel_id="c_1",
        channel_username="forex_signals_ar",
        channel_data=channel_data
    )
    assert job_id is not None
    assert mock_redis.lpush.called
