"""
tests/test_pattern_miner.py — Unit Tests for Contrastive Pattern Mining & Anti-Overfitting
"""

import pytest
from app.learning.pattern_miner import PatternMiner


class TestPatternMiner:

    def test_arabic_normalization(self):
        # Normalizes alefs, teh marbuta, yaa and strips diacritics
        text = "إشَارَاتُ التَّدَاوُلِ وَإِدَارَةُ المَحَافِظِ فِي الذَّهَبِ"
        norm = PatternMiner.normalize_arabic(text)
        assert "اشارات" in norm
        assert "اداره" in norm
        assert "المحافظ" in norm
        assert "الذهب" in norm
        assert "\u064e" not in norm  # Fatha removed

    def test_clean_text_strips_personal_and_urls(self):
        text = "Join @tamerads channel at https://t.me/example call +201012345678 for VIP توصيات فوركس"
        cleaned = PatternMiner.clean_text(text)
        assert "@tamerads" not in cleaned
        assert "https" not in cleaned
        assert "+201012345678" not in cleaned
        assert "توصيات فوركس" in cleaned

    def test_extract_symbols(self):
        text = "صفقة شراء XAUUSD الهدف 2650 و BTCUSDT عند 64000 و EURUSD للبيع"
        symbols = PatternMiner.extract_symbols(text)
        assert "XAUUSD" in symbols
        assert "BTCUSDT" in symbols
        assert "EURUSD" in symbols

    def test_log_odds_contrast_positive(self):
        # Signal appears in 8 out of 10 positive channels and 0 out of 20 negative channels
        contrast = PatternMiner.compute_log_odds_contrast(df_pos=8, n_pos=10, df_neg=0, n_neg=20)
        assert contrast > 2.0

    def test_log_odds_contrast_negative(self):
        # Signal appears in 0 out of 10 positive channels and 15 out of 20 negative channels (pure spam)
        contrast = PatternMiner.compute_log_odds_contrast(df_pos=0, n_pos=10, df_neg=15, n_neg=20)
        assert contrast < -2.0

    def test_anti_overfitting_rejects_single_channel_memorization(self):
        # Channel 1 has unique phrase "unique_personal_strategy"
        # Channel 2 has trading terms "توصيات الذهب"
        # Channel 3 has trading terms "توصيات الذهب"
        positive_corpus = [
            {
                "channel_username": "pos_1",
                "title": "قناة توصيات الذهب الرسمية",
                "about": "افضل توصيات الذهب xauusd",
                "posts": ["شراء xauusd الآن هدف اول", "unique_strategy_personal"]
            },
            {
                "channel_username": "pos_2",
                "title": "فوركس وذهب VIP",
                "about": "توصيات الذهب والعملات اليومية",
                "posts": ["شراء xauusd هدف ثاني 2680", "تحليل الذهب اليومي"]
            },
            {
                "channel_username": "pos_3",
                "title": "اكاديمية تداول الذهب",
                "about": "صفقات وتحليل فني xauusd",
                "posts": ["تحليل فني xauusd", "توصيات الذهب اليومية"]
            }
        ]

        negative_corpus = [
            {
                "channel_username": "neg_1",
                "title": "متجر شدات ببجي",
                "about": "شحن العاب وحسابات ببجي رخيصة",
                "posts": ["شدات ببجي مجانا"]
            },
            {
                "channel_username": "neg_2",
                "title": "افلام ومسلسلات netflix",
                "about": "اشتراكات نتفلكس وسيرفرات iptv",
                "posts": ["اشتراك iptv سنوي"]
            }
        ]

        mined = PatternMiner.mine_and_score(positive_corpus, negative_corpus)
        mined_values = {m["signal_value"] for m in mined}

        # Multi-channel features MUST be present
        assert any("xauusd" in v.lower() for v in mined_values)
        assert any("ذهب" in v for v in mined_values)

        # Single-channel feature MUST NOT be promoted (anti-overfitting)
        assert "unique_strategy_personal" not in mined_values
        assert not any("tamer" in v.lower() for v in mined_values)
