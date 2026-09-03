"""
app/scheduler/activity_classifier.py — Activity Intelligence & Classification Engine
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple


class ActivityClass:
    HOT = "HOT"         # Very active: >= 5 posts/day -> Crawl every 6 hours
    WARM = "WARM"       # Normal active: 1-4 posts/day -> Crawl every 24 hours
    COLD = "COLD"       # Low activity: < 1 post/week -> Crawl every 7 days
    DORMANT = "DORMANT" # Inactive: no posts > 30 days -> Crawl every 30 days

    CRAWL_INTERVALS = {
        HOT: timedelta(hours=6),
        WARM: timedelta(hours=24),
        COLD: timedelta(days=7),
        DORMANT: timedelta(days=30)
    }


class ActivityClassifier:
    """
    Analyzes historical message frequency and recency to classify channel activity tiers.
    """

    @staticmethod
    def classify_activity(
        posts_24h: int,
        posts_7d: int,
        posts_30d: int,
        last_post_at: Optional[datetime] = None
    ) -> Tuple[str, timedelta, datetime]:
        """
        Calculates activity classification and schedules next crawl timestamp.
        
        Returns:
            Tuple of (activity_class: str, interval: timedelta, next_crawl_at: datetime)
        """
        now = datetime.now(timezone.utc)

        # Check for dormancy
        if last_post_at:
            if last_post_at.tzinfo is None:
                last_post_at = last_post_at.replace(tzinfo=timezone.utc)
            days_since_last_post = (now - last_post_at).total_seconds() / 86400.0
            if days_since_last_post > 30:
                interval = ActivityClass.CRAWL_INTERVALS[ActivityClass.DORMANT]
                return ActivityClass.DORMANT, interval, now + interval

        # Classification logic based on frequency
        if posts_24h >= 5 or (posts_7d >= 35):
            act_class = ActivityClass.HOT
        elif posts_24h >= 1 or (posts_7d >= 7) or (posts_30d >= 20):
            act_class = ActivityClass.WARM
        elif posts_7d >= 1 or (posts_30d >= 4):
            act_class = ActivityClass.COLD
        else:
            act_class = ActivityClass.DORMANT

        interval = ActivityClass.CRAWL_INTERVALS[act_class]
        next_crawl = now + interval
        return act_class, interval, next_crawl
