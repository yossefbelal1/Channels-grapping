"""
tests/test_graph_importance_hardened.py — Test Suite for Graph Centrality & Forward Origin Hardening
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.graph.forward_analyzer import ForwardAnalyzer
from app.graph.graph_importance import GraphImportanceCalculator


def test_forward_analyzer_extracts_channel_id_without_username():
    # Simulate Telethon Message with fwd_from having from_id as PeerChannel but NO from_name
    class MockPeerChannel:
        def __init__(self, ch_id):
            self.channel_id = ch_id

    class MockFwd:
        def __init__(self):
            self.from_id = MockPeerChannel(1458920192)
            self.from_name = None
            self.channel_post = 42
            self.date = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    class MockMessage:
        def __init__(self):
            self.id = 999
            self.fwd_from = MockFwd()

    msg = MockMessage()
    origin = ForwardAnalyzer.extract_forward_origin(msg)

    assert origin is not None
    assert origin["is_forward"] is True
    assert origin["channel_id"] == "1458920192"
    assert origin["channel_post_id"] == 42
    assert origin["source_message_id"] == 999

    # Check explainable evidence (PART L)
    evidence = origin["evidence"]
    assert evidence["relation_type"] == "forwarded_from"
    assert evidence["source_message_id"] == 999
    assert evidence["original_channel_id"] == "1458920192"
    assert evidence["original_message_id"] == 42


def test_forward_analyzer_non_forward_returns_none():
    class MockMessage:
        def __init__(self):
            self.id = 100
            self.fwd_from = None

    msg = MockMessage()
    assert ForwardAnalyzer.extract_forward_origin(msg) is None


def test_graph_importance_scoring():
    # Hub channel with high in-degree, recommendations, forwards, and multiple discovery sources
    hub_res = GraphImportanceCalculator.calculate_importance_score(
        in_degree=25,
        out_degree=10,
        unique_relation_types=4,
        recommendation_in_count=6,
        forward_in_count=12,
        mention_in_count=7,
        discovery_source_count=3
    )
    assert hub_res["score"] >= 80
    assert hub_res["evidence"]["in_degree"] == 25
    assert hub_res["evidence"]["recommendation_in_count"] == 6

    # Isolated new channel with 0 edges
    isolated_res = GraphImportanceCalculator.calculate_importance_score(
        in_degree=0,
        out_degree=0,
        unique_relation_types=0,
        discovery_source_count=1
    )
    assert isolated_res["score"] <= 10
