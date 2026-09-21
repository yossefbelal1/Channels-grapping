"""
tests/test_exchange_network_engine.py — Comprehensive Test Suite for Exchange & Cross-Promotion Engine

Tests:
1. ExchangeAffinityAnalyzer: Arabic/English promo phrases, peer mentions, sweet spot sizing, seed/hub flags.
2. GoldAdminPatternProfiler: Signal format extraction, pairs detection, match scoring.
3. OutreachPriorityEngine: Prioritizing small/medium channels with verified contact & exchange affinity over giant passive channels.
"""

import pytest
from app.discovery.exchange_analyzer import ExchangeAffinityAnalyzer
from app.learning.gold_admin_pattern_profiler import GoldAdminPatternProfiler
from app.outreach.priority_engine import OutreachPriorityEngine
from app.outreach.constants import OutreachPriority


def test_exchange_phrases_and_peer_mentions():
    text_posts = [
        "صفقة شراء الذهب XAUUSD هدف 2740 ستوب 2720",
        "قناة صديقة ومتميزة ننصح بمتابعتها @alpha_gold_trade تبادل إعلاني متاح",
        "تابعوا القناة الشقيقة @forex_signals_pro شراكة حصرية"
    ]
    res = ExchangeAffinityAnalyzer.analyze_exchange_affinity(
        title="تداول الذهب والعملات",
        description="توصيات مجانية وتحليلات. للتواصل: @owner_trader",
        recent_messages=text_posts,
        member_count=5500,
        contact_username="owner_trader",
        has_verified_contact=True,
        forex_relevance_score=85
    )

    assert res["exchange_affinity_score"] >= 50
    assert res["growth_openness_score"] == 100  # 5.5k members is in prime sweet spot
    assert res["is_exchange_seed"] is True
    assert "alpha_gold_trade" in res["evidence"]["sample_peer_mentions"]
    assert "forex_signals_pro" in res["evidence"]["sample_peer_mentions"]
    assert len(res["evidence"]["matched_exchange_phrases"]) >= 2


def test_size_sweet_spot_curve():
    # 5,000 members -> 100 (Prime)
    score_5k, label_5k = ExchangeAffinityAnalyzer.calculate_size_sweet_spot(5000)
    assert score_5k == 100
    assert "optimal_prime_sweet_spot" in label_5k

    # 1,500 members -> 85
    score_1_5k, _ = ExchangeAffinityAnalyzer.calculate_size_sweet_spot(1500)
    assert score_1_5k == 85

    # 25,000 members -> 85
    score_25k, _ = ExchangeAffinityAnalyzer.calculate_size_sweet_spot(25000)
    assert score_25k == 85

    # 250,000 members (Giant) -> 20 (Low exchange receptivity)
    score_giant, label_giant = ExchangeAffinityAnalyzer.calculate_size_sweet_spot(250000)
    assert score_giant == 20
    assert "giant" in label_giant


def test_exchange_hub_qualification():
    res = ExchangeAffinityAnalyzer.analyze_exchange_affinity(
        title="دليل قنوات الفوركس",
        description="دعم وتبادل إعلاني لجميع القنوات",
        recent_messages=[
            "نوصي بمتابعة @chan1 و @chan2",
            "إعلان مؤقت لقناة @chan3 برعاية @chan4",
            "تبادل إعلاني مع @chan5"
        ],
        member_count=12000,
        contact_username="hub_admin",
        has_verified_contact=True,
        forex_relevance_score=60,
        out_degree=6
    )

    assert res["is_exchange_hub"] is True
    assert res["exchange_affinity_score"] >= 60


def test_gold_admin_pattern_profiler():
    trading_post = """
    صفقة شراء ذهب XAUUSD الآن
    الدخول: 2742.50
    الهدف الأول: 2748.00 (+55 نقطة)
    الهدف الثاني: 2755.00
    وقف الخسارة: 2736.00 (SL)
    إدارة رأس المال صارمة 1%
    """
    res = GoldAdminPatternProfiler.evaluate_against_profile(trading_post)
    assert res["match_score"] >= 50
    assert res["has_signal_structure"] is True
    assert "xauusd" in res["traded_pairs_found"] or "gold" in res["traded_pairs_found"]
    assert len(res["commentary_hits"]) >= 1


def test_priority_engine_small_mid_exchange_beats_giant_channel():
    # Channel A: 8,000 members, verified contact, active cross-promotion evidence
    small_exchange_channel = OutreachPriorityEngine.evaluate_priority(
        title="صياد الذهب | XAUUSD Signals",
        description="توصيات يومية. تواصل: @gold_hunter_admin",
        recent_messages=[
            "شراء XAUUSD هدف 2750 ستوب 2735",
            "نوصي بمتابعة قناة صديقة @expert_trading تبادل إعلاني",
        ],
        contacts_dict={"contact_username": "gold_hunter_admin", "source": "bio_official"},
        forex_relevance_score=80,
        member_count=8000,
        posts_24h=4,
        posts_7d=20
    )

    # Channel B: 300,000 members, no exchange evidence, generic contact
    giant_passive_channel = OutreachPriorityEngine.evaluate_priority(
        title="أخبار الاقتصاد العالمي",
        description="أخبار وتغطيات أسواق المال",
        recent_messages=[
            "ارتفاع مؤشرات الأسهم الأمريكية في تداولات الصباح",
            "تقرير أسبوعي عن التضخم والوظائف"
        ],
        contacts_dict={"contact_username": "media_corp", "source": "bio_general"},
        forex_relevance_score=50,
        member_count=300000,
        posts_24h=10,
        posts_7d=50
    )

    # Small active exchange candidate must be P0
    assert small_exchange_channel["priority"] == OutreachPriority.P0
    # Giant informational channel must NOT beat the small exchange channel
    assert giant_passive_channel["priority"] in (OutreachPriority.P2, OutreachPriority.P3)
    assert small_exchange_channel["priority_score"] > giant_passive_channel["priority_score"]
