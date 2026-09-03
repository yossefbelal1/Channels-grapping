"""
Unit tests for Arabic Normalizer & Query Variant Generator
"""

import pytest
from app.discovery.arabic_normalizer import (
    normalize_arabic_text,
    generate_query_variants,
    calculate_arabic_letter_ratio,
    contains_arabic
)


def test_normalize_arabic_alif_and_yaa():
    raw = "إشارات وتوصيات الذهب والمؤشرات أونصة"
    normalized = normalize_arabic_text(raw)
    assert "اشارات" in normalized
    assert "اونصه" in normalized
    assert "ا" in normalized


def test_strip_diacritics_and_tatweel():
    tashkeel_text = "فُورِكْسْ تَـدَاوُلْ"
    normalized = normalize_arabic_text(tashkeel_text)
    assert normalized == "فوركس تداول"


def test_contains_arabic():
    assert contains_arabic("توصيات فوركس") is True
    assert contains_arabic("Forex Arabic") is False
    assert contains_arabic("Forex عربي") is True


def test_calculate_arabic_letter_ratio():
    arabic_text = "قناة توصيات الذهب اليومية"
    ratio = calculate_arabic_letter_ratio(arabic_text)
    assert ratio >= 0.95

    mixed_text = "XAUUSD توصيات الذهب VIP"
    ratio_mixed = calculate_arabic_letter_ratio(mixed_text)
    assert 0.3 <= ratio_mixed <= 0.8


def test_generate_query_variants():
    kw = "توصيات الذهب"
    variants = generate_query_variants(kw, max_variants=4)
    assert len(variants) >= 2
    assert any("XAUUSD" in v for v in variants) or any("توصيات" in v for v in variants)
