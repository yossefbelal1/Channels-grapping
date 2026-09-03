"""
Unit tests for Multi-Edge Graph Manager
"""

import pytest
from unittest.mock import MagicMock
from app.graph.edge_manager import GraphEdgeManager, EdgeRelation


def test_edge_relation_constants():
    assert EdgeRelation.MENTION == "mention"
    assert EdgeRelation.FORWARDED_FROM == "forwarded_from"
    assert EdgeRelation.PROMOTED == "promoted"
    assert EdgeRelation.LINKED == "linked"
    assert EdgeRelation.RECOMMENDED == "recommended"


def test_record_edge_mocked_db():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mgr = GraphEdgeManager(db_conn=mock_conn)
    mgr.record_edge(
        source_channel_id="11111111-1111-1111-1111-111111111111",
        target_channel_id="22222222-2222-2222-2222-222222222222",
        relation_type=EdgeRelation.FORWARDED_FROM,
        confidence=95,
        evidence="Forwarded post excerpt"
    )

    assert mock_cursor.execute.called
    assert mock_conn.commit.called


def test_ignore_self_loops():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mgr = GraphEdgeManager(db_conn=mock_conn)
    mgr.record_edge(
        source_channel_id="11111111-1111-1111-1111-111111111111",
        target_channel_id="11111111-1111-1111-1111-111111111111",
        relation_type=EdgeRelation.MENTION
    )

    assert not mock_cursor.execute.called
