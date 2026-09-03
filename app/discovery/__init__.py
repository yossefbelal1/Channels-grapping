"""
app.discovery — Arabic Forex Discovery Intelligence & Normalization Package
"""

from app.discovery.arabic_normalizer import (
    normalize_arabic_text,
    generate_query_variants,
    calculate_arabic_letter_ratio,
    contains_arabic
)
from app.discovery.taxonomy import (
    KEYWORD_TAXONOMY,
    TAXONOMY_WEIGHTS,
    get_all_keywords,
    get_category_keywords,
    classify_text_taxonomy
)
from app.discovery.checkpoint import SearchCheckpointManager
from app.discovery.provenance import ProvenanceManager

__all__ = [
    "normalize_arabic_text",
    "generate_query_variants",
    "calculate_arabic_letter_ratio",
    "contains_arabic",
    "KEYWORD_TAXONOMY",
    "TAXONOMY_WEIGHTS",
    "get_all_keywords",
    "get_category_keywords",
    "classify_text_taxonomy",
    "SearchCheckpointManager",
    "ProvenanceManager"
]
