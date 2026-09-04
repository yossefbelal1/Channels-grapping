"""
app/scheduler/activity_classifier.py — Adaptive Crawl Scheduling & Activity Intelligence Engine

Production-Hardened Features:
- 5 Scheduling Tiers: HOT, WARM, NORMAL, COLD, DORMANT
- Adaptive calculate_next_crawl() balancing channel value, activity, graph importance, and failures
- Tiered Scan Depth budgets (deep, standard, incremental, light)
- Strict non-rejection: COOLDOWN/COLD/DORMANT are scheduling classes ONLY, never rejection/delete conditions
"""

import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple


class ActivityClass:
    HOT = "HOT"         # High-value and/or high activity -> Crawl every 2-6 hours
    WARM = "WARM"       # Good value / moderate activity -> Crawl every 12-24 hours
    NORMAL = "NORMAL"   # Standard channel -> Crawl every 2-4 days
    COLD = "COLD"       # Low activity but relevant -> Crawl every 7-14 days
    DORMANT = "DORMANT" # Very low activity / stale -> Crawl every 30 days

    ALL = [HOT, WARM, NORMAL, COLD, DORMANT]

    # Baseline intervals
    BASE_INTERVALS = {
        HOT: timedelta(hours=int(os.getenv("CRAWL_INTERVAL_HOT_HOURS", "4"))),
        WARM: timedelta(hours=int(os.getenv("CRAWL_INTERVAL_WARM_HOURS", "18"))),
        NORMAL: timedelta(days=int(os.getenv("CRAWL_INTERVAL_NORMAL_DAYS", "3"))),
        COLD: timedelta(days=int(os.getenv("CRAWL_INTERVAL_COLD_DAYS", "10"))),
        DORMANT: timedelta(days=int(os.getenv("CRAWL_INTERVAL_DORMANT_DAYS", "30")))
    }

    # Backward compatibility
    CRAWL_INTERVALS = {
        HOT: timedelta(hours=6),
        WARM: timedelta(hours=24),
        NORMAL: timedelta(days=3),
        COLD: timedelta(days=7),
        DORMANT: timedelta(days=30)
    }


class ScanDepthTier:
    DEEP = "deep"               # Promising/new or high-value: 100-200 posts
    STANDARD = "standard"       # Established/normal: 30-50 posts
    INCREMENTAL = "incremental" # Has watermark: only posts > watermark
    LIGHT = "light"             # Low-value or dormant: 10-15 posts


class ActivityClassifier:
    """
    Analyzes multi-dimensional signals, posting velocity, and graph importance
    to dynamically schedule incremental and deep channel crawling.
    """

    @staticmethod
    def classify_activity(
        posts_24h: int,
        posts_7d: int,
        posts_30d: int,
        last_post_at: Optional[datetime] = None
    ) -> Tuple[str, timedelta, datetime]:
        """
        Backward-compatible legacy classification based on post frequency.
        """
        now = datetime.now(timezone.utc)

        if last_post_at:
            if last_post_at.tzinfo is None:
                last_post_at = last_post_at.replace(tzinfo=timezone.utc)
            days_since_last_post = (now - last_post_at).total_seconds() / 86400.0
            if days_since_last_post > 30:
                interval = ActivityClass.CRAWL_INTERVALS[ActivityClass.DORMANT]
                return ActivityClass.DORMANT, interval, now + interval

        if posts_24h >= 5 or (posts_7d >= 35):
            act_class = ActivityClass.HOT
        elif posts_24h >= 1 or (posts_7d >= 7) or (posts_30d >= 20):
            act_class = ActivityClass.WARM
        elif posts_7d >= 1 or (posts_30d >= 4):
            act_class = ActivityClass.COLD
        else:
            act_class = ActivityClass.DORMANT

        interval = ActivityClass.CRAWL_INTERVALS[act_class]
        return act_class, interval, now + interval

    @classmethod
    def calculate_next_crawl(
        cls,
        final_score: int = 0,
        forex_score: int = 0,
        arabic_score: int = 0,
        activity_score: int = 0,
        freshness_score: int = 0,
        growth_score: int = 0,
        new_channel_score: int = 0,
        graph_importance_score: int = 0,
        discovery_count: int = 1,
        consecutive_failures: int = 0,
        posts_24h: int = 0,
        posts_7d: int = 0,
        posts_30d: int = 0,
        last_post_at: Optional[datetime] = None,
        last_crawl_at: Optional[datetime] = None,
        has_watermark: bool = False
    ) -> Dict[str, Any]:
        """
        Production-grade dynamic crawl interval calculator (PART A, B, C, D).

        Calculates:
        1. scheduling_tier: HOT | WARM | NORMAL | COLD | DORMANT
        2. interval_minutes: Adaptive interval bounded between min (120m) and max (43200m)
        3. next_crawl_at: Exact scheduled timestamp
        4. scan_depth_tier: deep | standard | incremental | light
        5. max_posts_budget: Max posts to request from Telegram

        IMPORTANT:
        DORMANT / COLD channels are scheduled with longer intervals, but NEVER rejected.
        """
        now = datetime.now(timezone.utc)

        # 1. Determine base scheduling tier
        # High value (Forex relevance + Arabic) or high activity or high graph centrality -> HOT
        is_high_value = (final_score >= 65 and forex_score >= 40) or (graph_importance_score >= 60)
        is_very_active = (posts_24h >= 6) or (posts_7d >= 30) or (activity_score >= 80)
        is_fresh = (freshness_score >= 80) or (last_post_at and (now - (last_post_at.replace(tzinfo=timezone.utc) if last_post_at.tzinfo is None else last_post_at)).total_seconds() <= 86400)

        # Check for dormancy (no posts in 30+ days)
        days_since_post = 0.0
        if last_post_at:
            lp = last_post_at.replace(tzinfo=timezone.utc) if last_post_at.tzinfo is None else last_post_at
            days_since_post = (now - lp).total_seconds() / 86400.0

        if days_since_post > 30 and posts_7d == 0 and posts_24h == 0:
            tier = ActivityClass.DORMANT
        elif is_high_value and (is_very_active or is_fresh or new_channel_score >= 30):
            tier = ActivityClass.HOT
        elif (final_score >= 45 and forex_score >= 25) or is_very_active or (graph_importance_score >= 35):
            tier = ActivityClass.WARM
        elif (final_score >= 30) or (posts_7d >= 3) or (activity_score >= 40):
            tier = ActivityClass.NORMAL
        elif (posts_30d >= 1) or (days_since_post <= 30):
            tier = ActivityClass.COLD
        else:
            tier = ActivityClass.DORMANT

        # 2. Adaptive interval calculation in minutes
        base_delta = ActivityClass.BASE_INTERVALS[tier]
        base_minutes = int(base_delta.total_seconds() / 60.0)

        # Modifier based on channel value & graph importance (higher value -> slightly faster crawl)
        value_factor = 1.0
        if final_score >= 75 or graph_importance_score >= 60:
            value_factor *= 0.75 # 25% faster
        elif final_score <= 25 and graph_importance_score <= 15:
            value_factor *= 1.35 # 35% slower

        # Modifier based on observed growth
        if growth_score >= 70:
            value_factor *= 0.8 # Active growth -> crawl faster to observe trajectory

        # Modifier based on new channel discovery (prioritize initial intelligence)
        if new_channel_score >= 30:
            value_factor *= 0.7

        # Failure penalty: consecutive failures trigger exponential backoff up to 4x
        failure_multiplier = 1.0
        if consecutive_failures > 0:
            failure_multiplier = min(4.0, 1.5 ** consecutive_failures)

        adaptive_minutes = int(base_minutes * value_factor * failure_multiplier)

        # Absolute boundaries: Min 2 hours (120m), Max 30 days (43200m)
        min_allowed = int(os.getenv("MIN_CRAWL_INTERVAL_MINUTES", "120"))
        max_allowed = int(os.getenv("MAX_CRAWL_INTERVAL_MINUTES", "43200"))
        adaptive_minutes = max(min_allowed, min(max_allowed, adaptive_minutes))

        next_crawl_at = now + timedelta(minutes=adaptive_minutes)

        # 3. Determine scan depth tier & budget
        if has_watermark:
            scan_depth = ScanDepthTier.INCREMENTAL
            max_posts = 100 # Telegram limit for incremental slice
        elif new_channel_score >= 30 or (tier == ActivityClass.HOT and final_score >= 70):
            scan_depth = ScanDepthTier.DEEP
            max_posts = 150 # Controlled deep scan for high-priority targets
        elif tier in [ActivityClass.WARM, ActivityClass.NORMAL]:
            scan_depth = ScanDepthTier.STANDARD
            max_posts = 40
        else:
            scan_depth = ScanDepthTier.LIGHT
            max_posts = 15

        return {
            "activity_class": tier,
            "scheduling_tier": tier,
            "interval_minutes": adaptive_minutes,
            "next_crawl_at": next_crawl_at,
            "scan_depth_tier": scan_depth,
            "max_posts_budget": max_posts
        }
