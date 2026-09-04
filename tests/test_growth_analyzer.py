"""
tests/test_growth_analyzer.py — Unit Tests for Observable Snapshot Growth Tracking
"""

import pytest
from datetime import datetime, timezone, timedelta
from app.scoring.growth_analyzer import GrowthAnalyzer


def test_growth_analyzer_insufficient_data():
    score, evidence = GrowthAnalyzer.calculate_growth_from_snapshots([])
    assert score == 0
    assert evidence["status"] == "UNOBSERVED_SNAPSHOTS"

    score, evidence = GrowthAnalyzer.calculate_growth_from_snapshots([
        {"member_count": 200, "recorded_at": datetime.now(timezone.utc)}
    ])
    assert score == 0
    assert evidence["status"] == "UNOBSERVED_SNAPSHOTS"


def test_growth_analyzer_rapid_growth():
    """
    Day 1: 200 members
    Day 4: 350 members
    Day 10: 800 members (+300% growth in 10 days) -> High growth score
    """
    t0 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(days=3)
    t2 = t0 + timedelta(days=9)

    snapshots = [
        {"member_count": 200, "recorded_at": t0},
        {"member_count": 350, "recorded_at": t1},
        {"member_count": 800, "recorded_at": t2}
    ]

    score, evidence = GrowthAnalyzer.calculate_growth_from_snapshots(snapshots)
    assert score >= 90
    assert evidence["status"] == "OBSERVED"
    assert evidence["growth_absolute"] == 600
    assert evidence["growth_percentage"] == 300.0
    assert evidence["member_count_t0"] == 200
    assert evidence["member_count_t1"] == 800


def test_growth_analyzer_negative_decline():
    """
    Member count dropping from 1000 to 700 (-30%)
    """
    t0 = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(days=15)

    snapshots = [
        {"member_count": 1000, "recorded_at": t0},
        {"member_count": 700, "recorded_at": t1}
    ]

    score, evidence = GrowthAnalyzer.calculate_growth_from_snapshots(snapshots)
    assert score <= 30
    assert evidence["growth_absolute"] == -300
    assert evidence["growth_percentage"] == -30.0
