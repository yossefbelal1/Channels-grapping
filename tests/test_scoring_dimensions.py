"""
Unit tests for 13-Dimension Lead Scoring Engine & Small/New Channel Prioritization
"""

from datetime import datetime, timezone, timedelta
import pytest
from app.scoring.dimensions import calculate_all_dimensions, ScoringDimensions


def test_small_channel_prioritization():
    """
    Ensures a small channel (150 subscribers) with high Forex & Gold signals
    scores high and is NOT rejected.
    """
    scores = calculate_all_dimensions(
        title="توصيات الذهب والعملات اليومية",
        description="صفقات سكالبينج فوركس يومية على XAUUSD مع تحديد وقف الخسارة والأهداف بدقة",
        recent_posts=[
            "صفقة شراء ذهب XAUUSD الآن هدف 2650 ستوب 2630",
            "تحليل الفوركس والعملات اليومي وتحديد مناطق الدخول",
            "ضرب الهدف الأول بنجاح +50 نقطة فوركس"
        ],
        member_count=150,
        has_contact=True,
        contact_types=["whatsapp", "admin"],
        posts_24h=3,
        posts_7d=12,
        posts_30d=40
    )

    assert scores.forex_score >= 30
    assert scores.gold_score >= 30
    assert scores.signal_score >= 30
    assert scores.new_channel_score >= 50 # Small channel bonus active
    assert scores.final_score >= 50
    assert scores.tier in ["Tier_A", "Tier_B"]


def test_new_channel_bonus():
    """
    Ensures newly created channels receive a new_channel_score boost.
    """
    now = datetime.now(timezone.utc)
    scores = calculate_all_dimensions(
        title="قناة تداول فوركس SMC جديدة",
        description="شروحات ICT وتحليل العملات",
        member_count=300,
        has_contact=True,
        creation_date=now - timedelta(days=10)
    )

    assert scores.new_channel_score >= 40
    assert scores.final_score >= 30


def test_anti_spam_legitimacy_penalty():
    """
    Ensures non-forex spam / casino / gambling drops legitimacy score to 0.
    """
    scores = calculate_all_dimensions(
        title="مراهنات وكازينو مباشر",
        description="ألعاب قمار وكازينو casino games",
        member_count=5000
    )

    assert scores.legitimacy_score < 70
    assert scores.final_score < 20
