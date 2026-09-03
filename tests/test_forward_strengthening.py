"""
tests/test_forward_strengthening.py — Unit Tests for Multi-Edge Graph Strengthening on Repeated Forwards
"""

import pytest
from unittest.mock import MagicMock
from app.graph.edge_manager import GraphEdgeManager, EdgeRelation
from app.graph.forward_analyzer import ForwardAnalyzer


def test_repeated_forwards_strengthen_edge():
    """
    Simulates Channel A forwarding from Channel B 5 times.
    Verifies that GraphEdgeManager records the edge each time with incrementing count.
    """
    mock_db = MagicMock()
    mock_cur = MagicMock()
    mock_db.cursor.return_value.__enter__.return_value = mock_cur

    edge_mgr = GraphEdgeManager(db_conn=mock_db)

    # 1st Forward
    edge_mgr.record_edge(
        source_channel_id="src_uuid_1",
        target_channel_id="target_uuid_2",
        relation_type=EdgeRelation.FORWARDED_FROM,
        confidence=80,
        evidence="Forwarded Trade 1"
    )
    assert mock_cur.execute.call_count >= 1

    # Simulate 4 more forwards
    for i in range(2, 6):
        edge_mgr.record_edge(
            source_channel_id="src_uuid_1",
            target_channel_id="target_uuid_2",
            relation_type=EdgeRelation.FORWARDED_FROM,
            confidence=80,
            evidence=f"Forwarded Trade {i}"
        )

    # Total executions: 5 calls x 2 inserts (edges + legacy graph) = 10 queries
    assert mock_cur.execute.call_count == 10
    assert mock_db.commit.call_count == 5


def test_forward_analyzer_extract_origin():
    """
    Tests extraction of origin peer ID and title from Telethon fwd_from structure.
    """
    mock_msg = MagicMock()
    mock_msg.fwd_from = MagicMock()
    mock_msg.fwd_from.from_id = MagicMock()
    mock_msg.fwd_from.from_id.channel_id = 998877
    mock_msg.fwd_from.from_name = "Master Signal Provider"

    origin = ForwardAnalyzer.extract_forward_origin(mock_msg)
    assert origin is not None
    assert origin["channel_id"] == "998877"
    assert origin["from_name"] == "Master Signal Provider"
