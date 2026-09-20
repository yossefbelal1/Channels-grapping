"""
tests/test_relevance_evaluator.py — Unit tests for RelevanceEvaluator
"""

import pytest
from app.discovery.relevance_evaluator import RelevanceEvaluator, RelevanceDecision


class TestRelevanceEvaluator:

    def test_hard_disqualifiers_betting(self):
        samples = [
            "قناة 1xbet الرسمية لربح المراهنات الرياضية",
            "افضل كازينو اونلاين وسلوتس وبوكر مباشر",
            "Melbet casino bonus 100% free spins and bookmaker",
            "Wolf bet daily bets and high odds"
        ]
        for text in samples:
            is_disq, term = RelevanceEvaluator.is_hard_disqualified(text)
            assert is_disq is True, f"Expected '{text}' to be disqualified by betting terms"
            assert term is not None

    def test_hard_disqualifiers_gaming(self):
        samples = [
            "متجر شدات ببجي رخيص وسريع شحن حسابات ببجي موبايل",
            "حسابات فورتنايت نادرة ومفتوحة مع رقصات",
            "شحن جواهر فري فاير مجانا robux free fire",
            "Minecraft and Roblox accounts cheap steam key"
        ]
        for text in samples:
            is_disq, term = RelevanceEvaluator.is_hard_disqualified(text)
            assert is_disq is True, f"Expected '{text}' to be disqualified by gaming terms"
            assert term is not None

    def test_hard_disqualifiers_iptv_and_spam(self):
        samples = [
            "اشتراك IPTV بلس مع باقات افلام ومسلسلات ونتفلكس",
            "دعم قنوات وزيادة متابعين واعضاء تيليجرام حقيقيين",
            "فيزا وهمية وشروحات هكر وبروكسي مجاني"
        ]
        for text in samples:
            is_disq, term = RelevanceEvaluator.is_hard_disqualified(text)
            assert is_disq is True, f"Expected '{text}' to be disqualified by media/spam terms"

    def test_legitimate_forex_mixed_language_pp_traders(self):
        """Channels like Pp_traders posting XAUUSD signals in English/mixed with SL/TP."""
        title = "PP TRADERS | FOREX & GOLD SIGNALS"
        description = "Official VIP Signals. Daily Gold (XAUUSD) & US30 setups with SL and TP. Contact @pp_admin."
        posts = [
            "XAUUSD BUY NOW 2650.00 | SL: 2642.00 | TP1: 2658.00 | TP2: 2665.00",
            "Hit TP1 +80 pips running! Move SL to entry!",
            "VIP group subscription open for next week. Contact @pp_admin."
        ]
        decision = RelevanceEvaluator.evaluate(
            title=title,
            description=description,
            recent_posts=posts,
            referrer_is_tier_a=True,
            discovery_source="telegram_recommendations"
        )
        assert decision.is_qualified is True
        assert decision.relevance_score >= 65
        assert decision.classification in ("HIGH_CONFIDENCE_FOREX", "LIKELY_FOREX")
        assert decision.tier_estimate in ("Tier_A", "Tier_B")
        assert decision.target_queue == "queue:high"

    def test_legitimate_forex_pure_arabic(self):
        title = "توصيات الذهب والعملات - المتداول المحترف"
        description = "قناة متخصصة في تحليل الذهب XAUUSD وعملات الفوركس. إدارة محافظ وإشارات VIP يومية."
        posts = [
            "صفقة شراء الذهب من 2630 الهدف 2645 وقف الخسارة 2622",
            "تحليل شارت الذهب فريم 4 ساعات: ارتداد من منطقة طلب قوية",
            "باقات الاشتراك في الجروب الخاص VIP متاحة الان"
        ]
        decision = RelevanceEvaluator.evaluate(
            title=title,
            description=description,
            recent_posts=posts
        )
        assert decision.is_qualified is True
        assert decision.relevance_score >= 60
        assert decision.target_queue == "queue:high"

    def test_smc_ict_methodology_channel(self):
        title = "SMC & ICT Arabic Traders"
        description = "Smart Money Concepts & Order Block analysis. Liquidity sweeps, FVG and market structure."
        posts = [
            "EURUSD 15m Fair Value Gap tapped. Looking for market structure shift (MSS).",
            "Bearish order block mitigated. Target sell side liquidity."
        ]
        decision = RelevanceEvaluator.evaluate(
            title=title,
            description=description,
            recent_posts=posts
        )
        assert decision.is_qualified is True
        assert decision.relevance_score >= 40
        assert decision.evidence["smc_terms_count"] >= 1

    def test_subscriber_neutrality(self):
        """Subscriber count must never act as a hard disqualifier."""
        # Small channel (e.g. 50 members) with real forex setups
        decision = RelevanceEvaluator.evaluate(
            title="Gold Scalping Alpha",
            description="Daily XAUUSD setups and live scalp calls. SL/TP included.",
            recent_posts=["BUY XAUUSD 2640 SL 2635 TP 2650"]
        )
        assert decision.is_qualified is True
        assert decision.relevance_score >= 50

    def test_graph_provenance_boost(self):
        """A recommendation originating from a Tier A channel receives a confidence boost."""
        base_decision = RelevanceEvaluator.evaluate(
            title="Forex Academy Insights",
            description="Technical analysis of currency markets",
            recent_posts=["Weekly outlook on EURUSD and GBPUSD"],
            referrer_is_tier_a=False
        )
        boosted_decision = RelevanceEvaluator.evaluate(
            title="Forex Academy Insights",
            description="Technical analysis of currency markets",
            recent_posts=["Weekly outlook on EURUSD and GBPUSD"],
            referrer_is_tier_a=True
        )
        assert boosted_decision.relevance_score >= base_decision.relevance_score + 15

    def test_crypto_arabic_channel_qualification(self):
        """Crypto channels with BTC/ETH signals, Binance/Bybit or leverage should qualify for high queue."""
        decision = RelevanceEvaluator.evaluate(
            title="توصيات بينانس كريبتو VIP",
            description="تحليل وتوصيات عملات رقمية وفيوتشر على منصة بينانس وباي بيت. صفقات BTC و ETH مع إدارة مخاطر.",
            recent_posts=[
                "صفقة شراء BTCUSDT دخول 62500 أهداف 64000 و 66000 وقف خسارة 61200 رافعة 10x",
                "تحليل الايثيريوم ETH: كسر منطقة المقاومة والهدف القادم 2750$"
            ]
        )
        assert decision.is_qualified is True
        assert decision.relevance_score >= 60
        assert decision.target_queue == "queue:high"

