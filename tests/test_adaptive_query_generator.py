"""
tests/test_adaptive_query_generator.py — Unit Tests for 80/20 Exploit/Explore Query Generator
"""

import pytest
from app.learning.knowledge_model import KnowledgeModel
from app.learning.adaptive_query_generator import AdaptiveQueryGenerator


class TestAdaptiveQueryGenerator:

    def test_fallback_when_model_is_empty(self):
        empty_model = KnowledgeModel()
        queries = AdaptiveQueryGenerator.generate_queries(empty_model, count=5)
        assert len(queries) == 5
        assert all(q["strategy"] == "fallback" for q in queries)
        assert all(len(q["query"]) > 3 for q in queries)

    def test_80_20_exploit_and_explore_distribution(self):
        model = KnowledgeModel()
        model.active_phrases = {
            "توصيات ذهب", "تحليل فوركس", "صفقات كريبتو vip",
            "ادارة محافظ فوركس", "تداول البيتكوين", "xauusd signals"
        }
        model.active_symbols = {"XAUUSD", "BTCUSDT", "EURUSD", "ETHUSDT"}
        model.active_keywords = {"فوركس", "ذهب", "تداول", "تحليل"}

        model.candidate_phrases = {"استراتيجية سمارت موني", "سكالبينج العملات"}
        model.candidate_keywords = {"فوليوم", "مقاومات"}

        queries = AdaptiveQueryGenerator.generate_queries(model, count=10, exploit_ratio=0.8)
        assert len(queries) == 10

        exploit_queries = [q for q in queries if q["strategy"] == "exploit"]
        explore_queries = [q for q in queries if q["strategy"] == "explore"]

        # Exploit should be roughly 80% (around 7-8 out of 10)
        assert len(exploit_queries) >= 6
        # Explore should be present (around 2-3 out of 10)
        assert len(explore_queries) >= 1

        # Check that query strings are non-empty and diverse
        unique_queries = {q["query"] for q in queries}
        assert len(unique_queries) == len(queries)
