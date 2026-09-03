"""
Unit tests for Candidate Identity, Provenance & Deduplication
"""

from unittest.mock import MagicMock
from app.discovery.provenance import ProvenanceManager


def test_canonical_username_normalization():
    assert ProvenanceManager.canonical_username("https://t.me/Forex_Arabic") == "forex_arabic"
    assert ProvenanceManager.canonical_username("@Forex_Arabic") == "forex_arabic"
    assert ProvenanceManager.canonical_username("t.me/Forex_Arabic?start=ref123") == "forex_arabic"
    assert ProvenanceManager.canonical_username("forex_arabic") == "forex_arabic"


def test_record_candidate_discovery():
    mock_redis = MagicMock()
    mock_redis.sadd.return_value = 1
    mock_redis.incr.return_value = 1
    mock_redis.smembers.return_value = {b"global_search"}

    prov = ProvenanceManager(redis_conn=mock_redis)
    is_new, count, sources = prov.record_candidate_discovery(
        username_or_link="https://t.me/ArabicForexSignals",
        source_type="global_search",
        keyword="توصيات فوركس"
    )

    assert is_new is True
    assert count == 1
    assert "global_search" in sources
