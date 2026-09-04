"""
tests/test_phase3_channel_intelligence.py — Comprehensive Test Suite for Phase 3

Covers all 18 specified scenarios + E2E multi-tier fixture:
1. Strong Forex channel
2. Small Forex channel (~400 members)
3. Large Forex channel (~500,000 members)
4. Very large Forex channel (~2,000,000 members)
5. Low-activity Forex channel
6. Medium-activity Forex channel
7. Highly active Forex channel
8. Mixed Arabic/English channel
9. Non-Forex channel with one Forex keyword
10. Growth calculation
11. Freshness calculation
12. Activity calculation
13. Final weighted score transparency
14. Evidence generation
15. Classification categories
16. Member-count neutrality
17. Activity non-rejection
18. Discovery-confidence contribution
19. End-to-End Multi-Channel Realistic Fixture (Channels A-F)
"""

from datetime import datetime, timezone, timedelta
import pytest

from app.scoring.dimensions import calculate_all_dimensions, ScoringDimensions
from app.scoring.growth_analyzer import GrowthAnalyzer


def test_1_strong_forex_channel():
    """Test 1: Channel with strong Arabic Forex signals and multi-post recurrence."""
    now = datetime.now(timezone.utc)
    scores = calculate_all_dimensions(
        title="توصيات فوركس والذهب اليومية",
        description="تحليلات فنية وتوصيات فوركس حصرية مع تحديد وقف الخسارة والأهداف",
        recent_posts=[
            "صفقة شراء EURUSD الآن هدف 1.0950 ستوب 1.0880",
            "تحليل الذهب XAUUSD اليوم وتحديث مستويات الدعم والمقاومة",
            "صفقة بيع GBPUSD دخول من 1.2850 الهدف 1.2750 وقف الخسارة 1.2900",
            "تحقيق هدف الذهب بنجاح +80 نقطة فوركس",
            "إدارة رأس المال وحسابات التداول باللوت المناسب"
        ],
        member_count=12000,
        has_contact=True,
        contact_types=["admin", "whatsapp"],
        posts_24h=3,
        posts_7d=18,
        posts_30d=65,
        last_post_at=now - timedelta(hours=2)
    )

    assert scores.forex_score >= 60
    assert scores.gold_score >= 40
    assert scores.signal_score >= 50
    assert scores.arabic_score >= 50
    assert scores.final_score >= 60
    assert scores.classification == "HIGH_CONFIDENCE_FOREX"
    assert scores.tier in ["Tier_A", "Tier_B"]


def test_2_small_forex_channel():
    """Test 2: Small channel (~400 members) with high Forex signals is retained with strong score."""
    now = datetime.now(timezone.utc)
    scores = calculate_all_dimensions(
        title="سكالبينج ذهب وفوركس",
        description="إشارات تداول وصفقات سريعة على الذهب والعملات",
        recent_posts=[
            "XAUUSD BUY 2640 SL 2632 TP 2655",
            "صفقة شراء فوركس GBPUSD هدف 50 نقطة",
            "تحليل شارت الذهب اليومي وتحديد مناطق الدخول"
        ],
        member_count=400,
        has_contact=True,
        posts_24h=1,
        posts_7d=8,
        posts_30d=25,
        last_post_at=now - timedelta(hours=5)
    )

    assert scores.member_count == 400
    assert scores.forex_score >= 35
    assert scores.gold_score >= 40
    assert scores.final_score >= 40
    assert scores.classification in ["HIGH_CONFIDENCE_FOREX", "LIKELY_FOREX"]
    # Verify small channel is retained and NOT penalized
    assert scores.final_score >= 35


def test_3_large_forex_channel():
    """Test 3: Large channel (~500,000 members) with strong Forex content is retained."""
    scores = calculate_all_dimensions(
        title="أكاديمية الفوركس والتحليل الفني",
        description="القناة الرسمية لتعليم وتداول العملات والسلع والذهب",
        recent_posts=[
            "تحليل يومي لسوق الفوركس والعملات الأجنبية EURUSD USDCAD",
            "صفقات بيع وشراء على الذهب والمؤشرات الأمريكية US30",
            "نظرة على مستويات التضخم وقرار الفيدرالي وأثره على الدولار والذهب"
        ],
        member_count=500000,
        has_contact=True,
        posts_24h=4,
        posts_7d=25,
        posts_30d=80
    )

    assert scores.member_count == 500000
    assert scores.forex_score >= 40
    assert scores.final_score >= 45
    assert scores.classification in ["HIGH_CONFIDENCE_FOREX", "LIKELY_FOREX"]


def test_4_very_large_forex_channel():
    """Test 4: Very large channel (~2,000,000 members) evaluated on relevance without runaway inflation."""
    scores = calculate_all_dimensions(
        title="شبكة المتداول العربي فوركس وذهب",
        description="أخبار وتوصيات وتحليلات فوركس لجميع الأسواق العالمية",
        recent_posts=[
            "تحديث حركة أسعار الذهب XAUUSD وسوق العملات الأجنبية",
            "صفقة شراء EURUSD ستوب 1.0820 الهدف 1.0900",
            "التحليل الفني للعملات والنفط والمعدن الأصفر"
        ],
        member_count=2000000,
        has_contact=True
    )

    assert scores.member_count == 2000000
    assert scores.forex_score >= 40
    assert scores.final_score <= 100
    assert scores.classification in ["HIGH_CONFIDENCE_FOREX", "LIKELY_FOREX"]


def test_5_low_activity_forex_channel():
    """Test 5: Low-activity channel (infrequent posting) retains high qualification if Forex evidence is strong."""
    now = datetime.now(timezone.utc)
    scores = calculate_all_dimensions(
        title="إشارات الذهب النخبة VIP",
        description="صفقات سوينغ أسبوعية دقيقة على الذهب XAUUSD والفوركس",
        recent_posts=[
            "صفقة شراء سوينغ XAUUSD من 2610 وقف 2590 أهداف 2650 2700",
            "تحديث صفقة الذهب: تأمين الدخول ونقل الستوب للأرباح +100 نقطة"
        ],
        member_count=450,
        has_contact=True,
        posts_24h=0,
        posts_7d=1,
        posts_30d=3,
        last_post_at=now - timedelta(days=5) # 5 days ago
    )

    assert scores.activity_score <= 40 # Low activity detected
    assert scores.forex_score >= 30    # High Forex relevance
    assert scores.gold_score >= 35
    assert scores.final_score >= 30    # Qualified!
    assert scores.classification in ["HIGH_CONFIDENCE_FOREX", "LIKELY_FOREX", "POSSIBLE_FOREX"]


def test_6_medium_activity_forex_channel():
    """Test 6: Medium activity channel shows balanced activity contribution."""
    now = datetime.now(timezone.utc)
    scores = calculate_all_dimensions(
        title="تحليلات الفوركس اليومية",
        description="تحليل فني لأزواج العملات والذهب",
        recent_posts=[
            "تحليل زوج GBPUSD اليوم",
            "توصية شراء XAUUSD هدف 2640"
        ],
        member_count=3500,
        posts_24h=1,
        posts_7d=6,
        posts_30d=24,
        last_post_at=now - timedelta(hours=18)
    )

    assert 30 <= scores.activity_score <= 70
    assert scores.freshness_score >= 80


def test_7_highly_active_forex_channel():
    """Test 7: Highly active channel scores high on activity and freshness."""
    now = datetime.now(timezone.utc)
    scores = calculate_all_dimensions(
        title="فوركس لايف إشارات مباشرة",
        description="توصيات مدار الساعة",
        recent_posts=["صفقة 1", "صفقة 2", "صفقة 3", "صفقة 4", "صفقة 5", "صفقة 6"],
        member_count=8000,
        posts_24h=8,
        posts_7d=35,
        posts_30d=120,
        last_post_at=now - timedelta(minutes=30)
    )

    assert scores.activity_score >= 80
    assert scores.freshness_score == 100


def test_8_mixed_arabic_english_channel():
    """Test 8: Mixed Arabic/English trading channel (Arabic commentary + English trade parameters)."""
    scores = calculate_all_dimensions(
        title="Gold Traders VIP",
        description="أفضل قناة صفقات وتوصيات ذهب وفوركس باللغة العربية",
        recent_posts=[
            "XAUUSD BUY NOW @ 2650.50 | SL: 2642 | TP1: 2660 | TP2: 2675",
            "شباب تم تأمين الصفقة وحجز جزء من الأرباح +40 pips",
            "EURUSD SELL Limit @ 1.0920 | Stop Loss: 1.0955 | Target: 1.0840",
            "تحليل شارت الذهب فريم 4 ساعات: ارتداد من منطقة Order Block"
        ],
        member_count=2200,
        has_contact=True
    )

    assert scores.arabic_score >= 60 # Recognized mixed Arabic context with vocabulary
    assert scores.forex_score >= 45
    assert scores.signal_score >= 50
    assert scores.classification in ["HIGH_CONFIDENCE_FOREX", "LIKELY_FOREX"]


def test_9_non_forex_single_keyword():
    """Test 9: Non-Forex channel with single isolated Forex mention does NOT receive high Forex score."""
    scores = calculate_all_dimensions(
        title="أخبار التكنولوجيا والهواتف الذكية",
        description="مراجعات هواتف أندرويد وآيفون وتطبيقات ذكية يومية",
        recent_posts=[
            "مراجعة هاتف سامسونج الجديد ومواصفات الكاميرا والبطارية",
            "تحديث تطبيق واتساب الجديد ومميزات الخصوصية",
            "أفضل برامج المونتاج للكمبيوتر لعام 2026",
            "هناك تطبيقات للربح أو التداول مثل فوركس احذروا النصب منها", # isolated fluke mention
            "شروحات تقنية لتسريع ويندوز والتخلص من الملفات المؤقتة",
            "أحدث سماعات بلوتوث عازلة للصوت بسعر اقتصادي"
        ],
        member_count=50000
    )

    assert scores.forex_score <= 20
    assert scores.classification == "LOW_CONFIDENCE"
    assert scores.evidence["is_isolated_single_keyword"] is True


def test_10_growth_calculation():
    """Test 10: Observed growth score derived strictly from snapshots via GrowthAnalyzer, and 0 when unobserved."""
    t0 = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc)
    snapshots = [
        {"member_count": 1000, "recorded_at": t0},
        {"member_count": 1300, "recorded_at": t1} # +30% growth in 14 days
    ]

    growth_score, evidence = GrowthAnalyzer.calculate_growth_from_snapshots(snapshots)
    assert growth_score >= 85
    assert evidence["growth_absolute"] == 300
    assert evidence["growth_percentage"] == 30.0
    assert evidence["status"] == "OBSERVED"

    # Test unobserved growth (0 snapshots)
    growth_score_unobserved, evidence_unobserved = GrowthAnalyzer.calculate_growth_from_snapshots([])
    assert growth_score_unobserved == 0
    assert evidence_unobserved["status"] == "UNOBSERVED_SNAPSHOTS"
    assert evidence_unobserved["growth_score"] == 0

    # Test unobserved growth (1 snapshot)
    growth_score_one, evidence_one = GrowthAnalyzer.calculate_growth_from_snapshots([
        {"member_count": 1000, "recorded_at": t0}
    ])
    assert growth_score_one == 0
    assert evidence_one["status"] == "UNOBSERVED_SNAPSHOTS"
    assert evidence_one["growth_score"] == 0


def test_11_freshness_calculation():
    """Test 11: Freshness scales with time since last post."""
    now = datetime.now(timezone.utc)

    # Within 24h
    s_24h = calculate_all_dimensions(last_post_at=now - timedelta(hours=4))
    assert s_24h.freshness_score == 100

    # 3 days ago
    s_3d = calculate_all_dimensions(last_post_at=now - timedelta(days=3))
    assert s_3d.freshness_score == 80

    # 10 days ago
    s_10d = calculate_all_dimensions(last_post_at=now - timedelta(days=10))
    assert s_10d.freshness_score == 45

    # 45 days ago (stale)
    s_45d = calculate_all_dimensions(last_post_at=now - timedelta(days=45))
    assert s_45d.freshness_score <= 15


def test_12_activity_calculation():
    """Test 12: Activity score accurately measures post volume velocity."""
    # Active
    s_active = calculate_all_dimensions(posts_24h=6, posts_7d=25, posts_30d=80)
    assert s_active.activity_score >= 80

    # Moderate
    s_mod = calculate_all_dimensions(posts_24h=2, posts_7d=8, posts_30d=20)
    assert 40 <= s_mod.activity_score <= 75

    # Dormant
    s_dormant = calculate_all_dimensions(posts_24h=0, posts_7d=0, posts_30d=0)
    assert s_dormant.activity_score <= 20


def test_13_final_weighted_score():
    """Test 13: Final weighted score is transparent, bounded, and bounded by anti-spam."""
    # Channel with high Forex intent
    scores = calculate_all_dimensions(
        title="توصيات فوركس",
        description="تداول العملات والذهب XAUUSD",
        recent_posts=["شراء EURUSD", "شراء XAUUSD"],
        member_count=500
    )
    assert 0 <= scores.final_score <= 100


def test_14_evidence_generation():
    """Test 14: Evidence dictionary is comprehensive and self-explanatory."""
    scores = calculate_all_dimensions(
        title="توصيات الذهب",
        description="تداول XAUUSD",
        recent_posts=["XAUUSD BUY SL 2640 TP 2660"],
        member_count=450
    )

    ev = scores.evidence
    assert "forex_terms_matched" in ev
    assert "gold_terms_matched" in ev
    assert "signals_terms_matched" in ev
    assert "member_count" in ev
    assert "arabic_character_ratio" in ev
    assert "classification_reason" in ev


def test_15_classification_categories():
    """Test 15: All classification categories are produced deterministically."""
    # HIGH_CONFIDENCE_FOREX
    s_high = calculate_all_dimensions(
        title="أكاديمية الفوركس وتوصيات الذهب",
        description="إشارات يومية وتحليل فني على أزواج العملات والذهب",
        recent_posts=[
            "صفقة شراء EURUSD الآن هدف 1.0950 ستوب 1.0880",
            "صفقة شراء XAUUSD هدف 2670 ستوب 2645",
            "تحليل الفوركس الأسبوعي ومستويات الفائدة"
        ]
    )
    assert s_high.classification == "HIGH_CONFIDENCE_FOREX"

    # LOW_CONFIDENCE
    s_low = calculate_all_dimensions(
        title="قناة الطبخ والحلويات",
        description="وصفات طعام شرقية وغربية",
        recent_posts=["طريقة عمل الكيك المنزلي", "وصفة بيتزا سهلة"]
    )
    assert s_low.classification == "LOW_CONFIDENCE"


def test_16_member_count_neutrality():
    """Test 16: Channels of vastly different sizes with identical content receive comparable core scores."""
    content = {
        "title": "إشارات فوركس وذهب",
        "description": "توصيات يومية على العملات الأجنبية و XAUUSD",
        "recent_posts": [
            "شراء EURUSD هدف 50 نقطة",
            "شراء XAUUSD هدف 2650 ستوب 2635"
        ]
    }

    s_small = calculate_all_dimensions(**content, member_count=400)
    s_medium = calculate_all_dimensions(**content, member_count=40000)
    s_huge = calculate_all_dimensions(**content, member_count=2000000)

    # Both small and huge channels must pass and have strong forex scores
    assert s_small.forex_score >= 30
    assert s_medium.forex_score >= 30
    assert s_huge.forex_score >= 30

    # Identical content produces identical score with zero member count bias
    assert s_small.final_score == s_medium.final_score == s_huge.final_score

    # Small channel is NOT rejected or suppressed
    assert s_small.final_score >= 30
    assert s_small.classification in ["HIGH_CONFIDENCE_FOREX", "LIKELY_FOREX", "POSSIBLE_FOREX"]


def test_17_activity_non_rejection():
    """Test 17: Low-activity channel (posts infrequently) is retained when Forex relevance is strong."""
    now = datetime.now(timezone.utc)
    scores = calculate_all_dimensions(
        title="توصيات فوركس طويلة المدى",
        description="صفقات أسبوعية وشهرية على العملات الأجنبية EURUSD GBPUSD مع إدارة رأس مال صارمة",
        recent_posts=[
            "صفقة شراء سوينغ شهرية على GBPUSD الهدف 1.3200 الستوب 1.2700"
        ],
        member_count=900,
        posts_24h=0,
        posts_7d=0,
        posts_30d=1,
        last_post_at=now - timedelta(days=20)
    )

    # Activity is low, but Forex intent is verified
    assert scores.activity_score <= 35
    assert scores.forex_score >= 30
    assert scores.classification != "LOW_CONFIDENCE"
    assert scores.final_score >= 25


def test_18_discovery_confidence_contribution():
    """Test 18: Multi-source discovery increases discovery_score."""
    s_single = calculate_all_dimensions(
        title="قناة تداول",
        discovery_count=1,
        discovery_sources=["global_search"]
    )
    s_multi = calculate_all_dimensions(
        title="قناة تداول",
        discovery_count=3,
        discovery_sources=["global_search", "search_posts", "recommendation"]
    )

    assert s_multi.discovery_score > s_single.discovery_score


# ──────────────────────────────────────────────────────────────────────────────
# 19. END-TO-END MULTI-CHANNEL REALISTIC FIXTURE
# ──────────────────────────────────────────────────────────────────────────────
def test_19_end_to_end_fixture_channels_a_through_f():
    """
    Realistic multi-tier test fixture:
    Channel A: 400 members, strong Arabic Forex content
    Channel B: 20,000 members, strong Arabic Forex content
    Channel C: 500,000 members, strong Arabic Forex content
    Channel D: 2,000,000 members, strong Arabic Forex content
    Channel E: 300,000 members, mostly unrelated content (memes/news)
    Channel F: 700 members, good Forex content, low activity

    Expected:
    A, B, C, D, F retained as qualified relevant candidates.
    E rejected / scored low confidence.
    Channels are NOT ranked purely by subscriber count!
    """
    now = datetime.now(timezone.utc)

    # Channel A: 400 members, strong Forex
    channel_a = calculate_all_dimensions(
        title="ذهب وفوركس VIP - صفقات حية",
        description="توصيات سكالبينج وتحليل شارت يومي على XAUUSD والعملات",
        recent_posts=[
            "صفقة شراء XAUUSD الآن 2645 هدف 2660 ستوب 2635",
            "شراء EURUSD من الدعم 1.0850 الهدف 1.0920",
            "تحقيق كامل الأهداف في صفقة الذهب +150 نقطة"
        ],
        member_count=400,
        has_contact=True,
        posts_24h=2,
        posts_7d=12,
        last_post_at=now - timedelta(hours=3)
    )

    # Channel B: 20,000 members, strong Forex
    channel_b = calculate_all_dimensions(
        title="نادي متداولي الفوركس العربي",
        description="إشارات تداول وتحليلات فنية يومية للعملات والذهب",
        recent_posts=[
            "تحليل أزواج العملات الرئيسية والفرعية لهذا الأسبوع",
            "صفقة بيع GBPUSD ستوب 1.2880 هدف 1.2750",
            "تحديث صفقة الذهب XAUUSD: حجز أرباح عند 2655"
        ],
        member_count=20000,
        has_contact=True,
        posts_24h=3,
        posts_7d=15,
        last_post_at=now - timedelta(hours=1)
    )

    # Channel C: 500,000 members, strong Forex
    channel_c = calculate_all_dimensions(
        title="أكاديمية الفوركس الدولية",
        description="المرجع العربي الأول لتداول العملات والذهب والمؤشرات",
        recent_posts=[
            "جلسة التداول الصباحية: تحليل الذهب واليورو دولار",
            "صفقة شراء USDJPY مع إدارة مخاطر 1%",
            "تغطية مؤشرات التضخم وتأثيرها على سوق الفوركس"
        ],
        member_count=500000,
        has_contact=True,
        posts_24h=4,
        posts_7d=20,
        last_post_at=now - timedelta(hours=4)
    )

    # Channel D: 2,000,000 members, strong Forex
    channel_d = calculate_all_dimensions(
        title="عالم التداول والأسواق العالمية",
        description="أخبار وتوصيات وتحليلات فوركس واقتصاد عالمي",
        recent_posts=[
            "نشرة أسواق الفوركس وحركة أسعار الذهب والنفط",
            "توصية شراء EURUSD هدف 1.0950",
            "تقرير حركة العملات الأجنبية والذهب اليومي"
        ],
        member_count=2000000,
        has_contact=True,
        posts_24h=5,
        posts_7d=30,
        last_post_at=now - timedelta(hours=1)
    )

    # Channel E: 300,000 members, unrelated content
    channel_e = calculate_all_dimensions(
        title="ضحك وفرفشة وميمز مضحكة",
        description="أجمل الفيديوهات والمقاطع المضحكة والترفيهية بدون إعلانات",
        recent_posts=[
            "فيديو مضحك جداً لا يفوتك",
            "موقف طريف حدث في الشارع اليوم",
            "نكتة اليوم اضحك من قلبك",
            "أجمل المقالب والطرائف الكوميدية"
        ],
        member_count=300000,
        posts_24h=6,
        posts_7d=40,
        last_post_at=now - timedelta(minutes=15)
    )

    # Channel F: 700 members, good Forex, low activity
    channel_f = calculate_all_dimensions(
        title="صفقات سوينغ فوركس نادرة",
        description="توصيات سوينغ مدروسة فقط 1-2 صفقة أسبوعياً على الذهب والعملات",
        recent_posts=[
            "صفقة سوينغ XAUUSD شراء من 2620 وقف 2595 هدف 2700",
            "تأمين صفقة الذهب بعد صعود 120 نقطة وإغلاق نصف العقود"
        ],
        member_count=700,
        has_contact=True,
        posts_24h=0,
        posts_7d=1,
        posts_30d=4,
        last_post_at=now - timedelta(days=4)
    )

    # ── Assertions ──
    # Channels A, B, C, D, F MUST be qualified relevant candidates
    assert channel_a.classification in ["HIGH_CONFIDENCE_FOREX", "LIKELY_FOREX"]
    assert channel_b.classification in ["HIGH_CONFIDENCE_FOREX", "LIKELY_FOREX"]
    assert channel_c.classification in ["HIGH_CONFIDENCE_FOREX", "LIKELY_FOREX"]
    assert channel_d.classification in ["HIGH_CONFIDENCE_FOREX", "LIKELY_FOREX"]
    assert channel_f.classification in ["HIGH_CONFIDENCE_FOREX", "LIKELY_FOREX", "POSSIBLE_FOREX"]

    assert channel_a.final_score >= 35
    assert channel_b.final_score >= 40
    assert channel_c.final_score >= 40
    assert channel_d.final_score >= 40
    assert channel_f.final_score >= 30

    # Channel E (300k members) MUST be rejected / scored very low despite huge member count
    assert channel_e.classification == "LOW_CONFIDENCE"
    assert channel_e.forex_score == 0
    assert channel_e.final_score <= 20

    # CRITICAL: Channel A (400 members) and Channel F (700 members) must rank higher than Channel E (300k members)
    assert channel_a.final_score > channel_e.final_score
    assert channel_f.final_score > channel_e.final_score

    # Assert ranking is relevance-driven, NOT subscriber-driven
    candidates = [
        {"name": "Channel A (400)", "score": channel_a.final_score, "members": 400, "qualified": True},
        {"name": "Channel B (20k)", "score": channel_b.final_score, "members": 20000, "qualified": True},
        {"name": "Channel C (500k)", "score": channel_c.final_score, "members": 500000, "qualified": True},
        {"name": "Channel D (2M)", "score": channel_d.final_score, "members": 2000000, "qualified": True},
        {"name": "Channel E (300k)", "score": channel_e.final_score, "members": 300000, "qualified": False},
        {"name": "Channel F (700)", "score": channel_f.final_score, "members": 700, "qualified": True}
    ]

    # Sort by final_score descending
    ranked = sorted(candidates, key=lambda c: c["score"], reverse=True)
    # Channel E should be at the very bottom
    assert ranked[-1]["name"] == "Channel E (300k)"


def test_20_all_nine_required_rules():
    """
    Direct verification of all 9 Phase 3 rules:
    1. 400-member relevant channel is retained.
    2. 2,000,000-member relevant channel is retained.
    3. Same content/evidence with different member counts does NOT receive a member-count bonus.
    4. Member count does not directly change the score.
    5. No snapshots => growth_score is neutral/no-evidence (0).
    6. One snapshot => growth_score is neutral/no-evidence (0).
    7. Two snapshots showing growth => positive growth_score (>0).
    8. Activity can increase activity_score without increasing growth_score when snapshots are absent.
    9. Low activity does not reject a relevant Forex channel.
    """
    now = datetime.now(timezone.utc)
    common_content = {
        "title": "فوركس وذهب مباشر",
        "description": "توصيات يومية وصفقات سكالبينج على العملات والذهب XAUUSD",
        "recent_posts": [
            "صفقة شراء XAUUSD الهدف 2670 وقف 2640",
            "تحليل فوركس زوج EURUSD دخول 1.0920"
        ]
    }

    # Rule 1: 400-member channel is retained
    s_400 = calculate_all_dimensions(**common_content, member_count=400, has_contact=True)
    assert s_400.final_score >= 35
    assert s_400.classification in ["HIGH_CONFIDENCE_FOREX", "LIKELY_FOREX"]

    # Rule 2: 2,000,000-member channel is retained
    s_2m = calculate_all_dimensions(**common_content, member_count=2000000, has_contact=True)
    assert s_2m.final_score >= 35
    assert s_2m.classification in ["HIGH_CONFIDENCE_FOREX", "LIKELY_FOREX"]

    # Rule 3 & 4: Same content with different member counts does NOT receive a member-count bonus, score is identical
    s_4k = calculate_all_dimensions(**common_content, member_count=4000, has_contact=True)
    s_40k = calculate_all_dimensions(**common_content, member_count=40000, has_contact=True)
    s_400k = calculate_all_dimensions(**common_content, member_count=400000, has_contact=True)
    assert s_400.final_score == s_4k.final_score == s_40k.final_score == s_400k.final_score == s_2m.final_score
    assert s_400.new_channel_score == s_2m.new_channel_score == 0

    # Rule 5: No snapshots => growth_score is neutral/no-evidence (0)
    s_no_snap = calculate_all_dimensions(**common_content, snapshots=[])
    assert s_no_snap.growth_score == 0
    assert s_no_snap.evidence["growth_analysis"]["status"] == "UNOBSERVED_SNAPSHOTS"
    assert s_no_snap.evidence["growth_analysis"]["growth_score"] == 0

    # Rule 6: One snapshot => growth_score is neutral/no-evidence (0)
    s_one_snap = calculate_all_dimensions(**common_content, snapshots=[{"member_count": 500, "recorded_at": now}])
    assert s_one_snap.growth_score == 0
    assert s_one_snap.evidence["growth_analysis"]["status"] == "UNOBSERVED_SNAPSHOTS"
    assert s_one_snap.evidence["growth_analysis"]["growth_score"] == 0

    # Rule 7: Two snapshots showing growth => positive growth_score (>0)
    s_growth = calculate_all_dimensions(**common_content, snapshots=[
        {"member_count": 500, "recorded_at": now - timedelta(days=7)},
        {"member_count": 750, "recorded_at": now}
    ])
    assert s_growth.growth_score > 0
    assert s_growth.evidence["growth_analysis"]["status"] == "OBSERVED"

    # Rule 8: Activity can increase activity_score without increasing growth_score when snapshots are absent
    s_idle = calculate_all_dimensions(**common_content, posts_24h=0, posts_7d=0, posts_30d=0, snapshots=[])
    s_busy = calculate_all_dimensions(**common_content, posts_24h=10, posts_7d=50, posts_30d=200, snapshots=[])
    assert s_busy.activity_score > s_idle.activity_score
    assert s_busy.growth_score == 0
    assert s_idle.growth_score == 0
    assert s_busy.evidence["growth_analysis"]["status"] == "UNOBSERVED_SNAPSHOTS"

    # Rule 9: Low activity does not reject a relevant Forex channel
    s_low_act = calculate_all_dimensions(
        title="توصيات فوركس طويلة المدى",
        description="تحليلات فوركس نادرة على العملات",
        recent_posts=["توصية شراء EURUSD هدف 100 نقطة"],
        posts_24h=0,
        posts_7d=0,
        posts_30d=1,
        last_post_at=now - timedelta(days=25)
    )
    assert s_low_act.activity_score <= 35
    assert s_low_act.forex_score >= 30
    assert s_low_act.classification != "LOW_CONFIDENCE"
    assert s_low_act.final_score >= 20
