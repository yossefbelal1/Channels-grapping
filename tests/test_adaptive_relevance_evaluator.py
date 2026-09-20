"""
tests/test_adaptive_relevance_evaluator.py — Unit Tests for Adaptive Relevance Evaluation
"""

import pytest
from app.learning.knowledge_model import KnowledgeModel
from app.discovery.relevance_evaluator import RelevanceEvaluator, RelevanceDecision


class TestAdaptiveRelevanceEvaluator:

    def test_knowledge_model_text_boost(self):
        model = KnowledgeModel()
        model.active_symbols = {"XAUUSD", "BTCUSDT"}
        model.active_phrases = {"توصيات ذهب", "تحليل فني"}
        model.active_keywords = {"فوركس", "سكالبينج"}

        text = "قناة متخصصة في توصيات ذهب و صفقات XAUUSD مع سكالبينج"
        boost, matched = model.evaluate_text_boost(text)

        assert boost > 0.0
        assert any("symbol:XAUUSD" in m for m in matched)
        assert any("phrase:توصيات ذهب" in m for m in matched)
        assert boost <= 20.0  # Capped at 20

    def test_relevance_evaluator_boosts_score_with_learned_model(self):
        model = KnowledgeModel()
        model.active_symbols = {"XAUUSD"}
        model.active_phrases = {"ادارة محافظ فوركس"}
        model.active_keywords = {"فوركس"}

        # Text with learned phrases
        decision_without_model = RelevanceEvaluator.evaluate(
            title="اكاديمية المحترفين",
            description="نقدم خدمات مالية متنوعة",
            username="pro_academy"
        )

        decision_with_model = RelevanceEvaluator.evaluate(
            title="اكاديمية المحترفين",
            description="نقدم ادارة محافظ فوركس مع XAUUSD",
            username="pro_academy",
            knowledge_model=model
        )

        assert decision_with_model.relevance_score > decision_without_model.relevance_score
        assert "learned_signals_boost" in decision_with_model.evidence
        assert decision_with_model.evidence["learned_signals_boost"] > 0

    def test_hard_disqualifier_overrides_learned_boost(self):
        # Even if text contains "XAUUSD" or "forex", a hard disqualifier (casino/betting/pubg) must reject immediately
        model = KnowledgeModel()
        model.active_symbols = {"XAUUSD"}

        decision = RelevanceEvaluator.evaluate(
            title="كازينو ومراهنات 1xbet توصيات xauusd",
            description="اربح من كازينو اونلاين",
            username="casino_xau",
            knowledge_model=model
        )

        assert decision.is_qualified is False
        assert decision.relevance_score == 0
        assert decision.classification == "REJECTED"
