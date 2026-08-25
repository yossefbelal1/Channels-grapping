"""
tests/test_scoring.py — Unit Tests for Arabic NLP & Lead Scoring
"""

import unittest
from app.validator.scoring import calculate_arabic_ratio, calculate_lead_score


class TestScoringEngine(unittest.TestCase):

    def test_arabic_ratio_pure_arabic(self):
        text = "قناة توصيات الفوركس والذهب اليومية لتحقيق الأرباح"
        ratio = calculate_arabic_ratio(text)
        self.assertGreaterEqual(ratio, 0.95)

    def test_arabic_ratio_english_text(self):
        text = "Daily Crypto Signals and Bitcoin Futures Trading Analysis"
        ratio = calculate_arabic_ratio(text)
        self.assertEqual(ratio, 0.0)

    def test_arabic_ratio_mixed_text(self):
        text = "توصيات VIP لصفقات XAUUSD و Bitcoin يومياً"
        ratio = calculate_arabic_ratio(text)
        self.assertGreater(ratio, 0.4)
        self.assertLess(ratio, 0.9)

    def test_calculate_tier_1_lead(self):
        commercial_flags = {
            "has_vip": True,
            "has_account_management": True,
            "has_copy_trading": True,
            "has_signals": True
        }
        score, tier = calculate_lead_score(
            member_count=15000,
            arabic_ratio=0.85,
            has_contact=True,
            commercial_flags=commercial_flags,
            has_recent_activity=True
        )
        self.assertGreaterEqual(score, 75)
        self.assertEqual(tier, "Tier 1")

    def test_calculate_unqualified_lead(self):
        commercial_flags = {}
        score, tier = calculate_lead_score(
            member_count=20,
            arabic_ratio=0.05,
            has_contact=False,
            commercial_flags=commercial_flags,
            has_recent_activity=False
        )
        self.assertLess(score, 30)
        self.assertEqual(tier, "Unqualified")


if __name__ == '__main__':
    unittest.main()
