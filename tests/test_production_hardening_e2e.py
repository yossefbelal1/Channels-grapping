"""
tests/test_production_hardening_e2e.py — End-to-End Test for Production Hardening Engine
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from app.scheduler.activity_classifier import ActivityClassifier, ActivityClass, ScanDepthTier
from app.scheduler.watermark_manager import WatermarkManager
from app.graph.forward_analyzer import ForwardAnalyzer
from app.graph.graph_importance import GraphImportanceCalculator
from app.core.telegram_pool import AccountState, AccountPoolManager, RetryPolicy
from app.core.reliability import JobEnvelope, IdempotencyGuard, DeadLetterQueueManager
from app.scoring.dimensions import calculate_all_dimensions


def test_production_hardening_full_cycle():
    # 1. Incoming channel with content
    title = "قناة توصيات الذهب والفوركس VIP"
    description = "توصيات يومية فوركس وذهب مع إدارة رأس المال XAUUSD EURUSD"
    recent_posts = [
        "صفقة شراء EURUSD دخول 1.0850 الهدف 1.0900 وقف الخسارة 1.0820",
        "تحديث الذهب XAUUSD حقق الهدف الأول +50 نقطة الحمد لله"
    ]

    # 2. Member-count neutrality check (Phase 3 Core Rule preserved in v7)
    score_small = calculate_all_dimensions(
        title=title, description=description, recent_posts=recent_posts, member_count=400
    )
    score_mid = calculate_all_dimensions(
        title=title, description=description, recent_posts=recent_posts, member_count=40000
    )
    score_huge = calculate_all_dimensions(
        title=title, description=description, recent_posts=recent_posts, member_count=2000000
    )

    assert score_small.final_score == score_mid.final_score == score_huge.final_score
    assert score_small.new_channel_score == score_huge.new_channel_score

    # 3. Dynamic crawl interval calculation (PART A, B, C, D)
    crawl_info = ActivityClassifier.calculate_next_crawl(
        final_score=score_small.final_score,
        forex_score=score_small.forex_score,
        arabic_score=score_small.arabic_score,
        activity_score=score_small.activity_score,
        freshness_score=score_small.freshness_score,
        growth_score=score_small.growth_score,
        new_channel_score=score_small.new_channel_score,
        graph_importance_score=50,
        posts_24h=2,
        posts_7d=14,
        has_watermark=True
    )
    assert crawl_info["scheduling_tier"] in [ActivityClass.HOT, ActivityClass.WARM]
    assert crawl_info["scan_depth_tier"] == ScanDepthTier.INCREMENTAL
    assert crawl_info["max_posts_budget"] == 100

    # 4. Forward Origin Extraction without public username (PART K, L)
    mock_msg = {
        "id": 105,
        "fwd_from": {
            "from_id": {"channel_id": "1892019"},
            "channel_post": 44,
            "date": datetime(2026, 2, 1, 10, 0, 0, tzinfo=timezone.utc)
        }
    }
    fwd = ForwardAnalyzer.extract_forward_origin(mock_msg)
    assert fwd is not None
    assert fwd["channel_id"] == "1892019"
    assert fwd["evidence"]["original_channel_id"] == "1892019"

    # 5. Graph Importance calculation (PART J)
    graph_res = GraphImportanceCalculator.calculate_importance_score(
        in_degree=8,
        out_degree=3,
        unique_relation_types=3,
        recommendation_in_count=2,
        forward_in_count=4,
        mention_in_count=2,
        discovery_source_count=2
    )
    assert graph_res["score"] >= 50

    # 6. Reliability & DLQ (PART N)
    job = JobEnvelope.wrap({"channel_username": "forex_gold_ar"}, max_attempts=3)
    assert job["job_id"] is not None
    assert job["attempt_count"] == 0
