"""
Unit tests for Arabic Forex Keyword Taxonomy & Text Classifier
"""

import pytest
from app.discovery.taxonomy import (
    KEYWORD_TAXONOMY,
    get_all_keywords,
    get_category_keywords,
    classify_text_taxonomy
)


def test_get_all_keywords():
    all_kws = get_all_keywords()
    assert len(all_kws) > 50
    assert "فوركس" in all_kws
    assert "ذهب" in all_kws or "الذهب" in all_kws
    assert "xauusd" in [k.lower() for k in all_kws]


def test_classify_text_taxonomy_forex():
    sample = "أقوى قناة توصيات فوركس في العالم العربي صفقات سكالبينج يومية على الذهب XAUUSD"
    hits = classify_text_taxonomy(sample)
    assert len(hits.get("FOREX", [])) >= 1
    assert len(hits.get("GOLD_XAUUSD", [])) >= 1
    assert len(hits.get("SIGNALS", [])) >= 1


def test_classify_text_smc_ict():
    smc_text = "تحليل SMC وشرح مفاهيم كورس ICT مع تحديد مناطق Order Block وسحب السيولة"
    hits = classify_text_taxonomy(smc_text)
    assert len(hits.get("SMC_ICT", [])) >= 2
