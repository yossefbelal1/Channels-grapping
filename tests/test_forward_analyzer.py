"""
Unit tests for Forward Origin Analyzer
"""

from unittest.mock import MagicMock
from app.graph.forward_analyzer import ForwardAnalyzer


def test_extract_forward_origin():
    mock_msg = MagicMock()
    mock_fwd = MagicMock()
    mock_fwd.from_name = "Forex Master VIP"
    mock_fwd.channel_post = 1234
    mock_msg.fwd_from = mock_fwd

    origin = ForwardAnalyzer.extract_forward_origin(mock_msg)
    assert origin is not None
    assert origin["from_name"] == "Forex Master VIP"
    assert origin["channel_post_id"] == 1234


def test_summarize_forwards():
    mock_msg1 = MagicMock()
    mock_msg1.fwd_from = MagicMock(from_name="Alpha Signals", channel_post=1)

    mock_msg2 = MagicMock()
    mock_msg2.fwd_from = MagicMock(from_name="Alpha Signals", channel_post=2)

    mock_msg3 = MagicMock()
    mock_msg3.fwd_from = None

    summary = ForwardAnalyzer.summarize_forwards([mock_msg1, mock_msg2, mock_msg3])
    assert summary["total_messages"] == 3
    assert summary["forwarded_count"] == 2
    assert summary["forward_ratio"] == 0.667
    assert summary["top_origins"][0]["origin_identifier"] == "Alpha Signals"
    assert summary["top_origins"][0]["count"] == 2
