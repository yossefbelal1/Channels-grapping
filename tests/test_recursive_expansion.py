"""
tests/test_recursive_expansion.py — Unit tests for Recursive Similar Channels Expansion
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from graph_expander import GraphExpander, MAX_RECURSIVE_DEPTH
from app.graph.edge_manager import EdgeRelation


class DummyChat:
    def __init__(self, username, title=""):
        self.username = username
        self.title = title
        self.broadcast = True


class DummyRecs:
    def __init__(self, chats):
        self.chats = chats


class TestRecursiveExpansion:

    @pytest.mark.asyncio
    async def test_depth_increment_and_queueing(self):
        """Source at depth=0 enqueues recommendations at depth=1."""
        mock_redis = MagicMock()
        mock_redis.lpop.side_effect = [
            json.dumps({"username": "tier_a_parent", "channel_id": "101", "depth": 0, "tier": "Tier_A"}),
            None
        ]
        mock_redis.sismember.return_value = False  # Not seen

        mock_tg = AsyncMock()
        parent_entity = DummyChat("tier_a_parent", "Forex VIP Official")
        mock_tg.execute_request.return_value = parent_entity

        child_chat = DummyChat("similar_forex_child", "Gold Scalping Signals XAUUSD")
        mock_tg.get_channel_recommendations.return_value = DummyRecs([child_chat])

        expander = GraphExpander()
        expander.redis_conn = mock_redis
        expander.tg_manager = mock_tg
        expander.insert_or_get_target_lead = MagicMock(return_value="202")
        expander.edge_mgr = MagicMock()
        expander.provenance_mgr = MagicMock()
        expander.shutdown_event = MagicMock(is_set=MagicMock(return_value=False))

        with patch("asyncio.sleep", new_callable=AsyncMock):
            processed = await expander.process_recommendations_queue(max_items=5)

        assert processed == 1
        # Verify target lead inserted with depth 1
        expander.insert_or_get_target_lead.assert_called_with("similar_forex_child", 1, "tier_a_parent")
        # Verify edge recorded
        expander.edge_mgr.record_edge.assert_called_once()
        # Verify queued item has depth 1
        queued_calls = mock_redis.rpush.call_args_list
        assert len(queued_calls) >= 1
        target_q, payload_raw = queued_calls[0][0]
        payload = json.loads(payload_raw)
        assert payload["depth"] == 1
        assert payload["source"] == "@tier_a_parent"
        assert payload["relation"] == EdgeRelation.RECOMMENDATION

    @pytest.mark.asyncio
    async def test_max_recursive_depth_gate(self):
        """Source at depth >= MAX_RECURSIVE_DEPTH is halted without Telegram recommendations API calls."""
        mock_redis = MagicMock()
        mock_redis.lpop.side_effect = [
            json.dumps({"username": "deep_leaf_channel", "channel_id": "999", "depth": MAX_RECURSIVE_DEPTH, "tier": "Tier_A"}),
            None
        ]
        mock_tg = AsyncMock()

        expander = GraphExpander()
        expander.redis_conn = mock_redis
        expander.tg_manager = mock_tg
        expander.shutdown_event = MagicMock(is_set=MagicMock(return_value=False))

        processed = await expander.process_recommendations_queue(max_items=5)
        # 0 Telegram recommendation API calls made
        mock_tg.get_channel_recommendations.assert_not_called()

    @pytest.mark.asyncio
    async def test_deduplication_records_edge_without_requeue(self):
        """Channels already in seen_channels get their graph edge recorded without duplicate queueing."""
        mock_redis = MagicMock()
        mock_redis.lpop.side_effect = [
            json.dumps({"username": "parent_chan", "channel_id": "111", "depth": 1, "tier": "Tier_B"}),
            None
        ]
        # Already seen
        mock_redis.sismember.return_value = True

        mock_tg = AsyncMock()
        parent_entity = DummyChat("parent_chan", "Parent Signals")
        mock_tg.execute_request.return_value = parent_entity

        child_chat = DummyChat("already_seen_forex", "Already Known Gold")
        mock_tg.get_channel_recommendations.return_value = DummyRecs([child_chat])

        expander = GraphExpander()
        expander.redis_conn = mock_redis
        expander.tg_manager = mock_tg
        expander.insert_or_get_target_lead = MagicMock(return_value="333")
        expander.edge_mgr = MagicMock()
        expander.provenance_mgr = MagicMock()
        expander.shutdown_event = MagicMock(is_set=MagicMock(return_value=False))

        with patch("asyncio.sleep", new_callable=AsyncMock):
            processed = await expander.process_recommendations_queue(max_items=5)

        assert processed == 1
        # Edge recorded to keep network graph topology intact
        expander.edge_mgr.record_edge.assert_called_once()
        # NOT queued again to prevent infinite loops
        mock_redis.rpush.assert_not_called()
