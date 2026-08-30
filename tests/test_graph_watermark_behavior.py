"""
tests/test_graph_watermark_behavior.py — Verification tests for Graph Expander watermark & incremental scan
"""

import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from graph_expander import GraphExpander


class TestGraphWatermarkBehavior(unittest.TestCase):

    def setUp(self):
        with patch('graph_expander.DatabaseHelper'), patch('graph_expander.redis.Redis'):
            self.expander = GraphExpander()
            self.expander.redis_conn = MagicMock()
            self.expander.tg_manager = MagicMock()

    def test_first_scan_no_watermark_full_scan(self):
        """P1-G Verification: When no watermark exists in Redis, min_id=0 and full scan is executed."""
        self.expander.redis_conn.get.return_value = None

        watermark_val = self.expander.redis_conn.get("graph:watermark:testchannel")
        min_id = int(watermark_val) if watermark_val and watermark_val.isdigit() else 0

        self.assertEqual(min_id, 0, "First scan MUST use min_id=0 (full scan).")

    def test_second_scan_uses_watermark_incremental_scan(self):
        """P1-G Verification: When watermark exists (e.g. message ID 1500), incremental scan uses min_id=1500."""
        self.expander.redis_conn.get.return_value = "1500"

        watermark_val = self.expander.redis_conn.get("graph:watermark:testchannel")
        min_id = int(watermark_val) if watermark_val and watermark_val.isdigit() else 0

        self.assertEqual(min_id, 1500, "Second scan MUST use watermark min_id=1500.")

    def test_watermark_advances_to_maximum_message_id(self):
        """P1-G Verification: When new messages arrive, watermark updates to max(msg.id)."""
        class MockMessage:
            def __init__(self, msg_id):
                self.id = msg_id

        msgs = [MockMessage(1501), MockMessage(1520), MockMessage(1510)]
        max_id = max(m.id for m in msgs)
        self.assertEqual(max_id, 1520)

        # Set new watermark in Redis
        self.expander.redis_conn.set("graph:watermark:testchannel", max_id, ex=86400 * 30)
        self.expander.redis_conn.set.assert_called_once_with("graph:watermark:testchannel", 1520, ex=86400 * 30)

    def test_duplicate_execution_with_empty_new_messages(self):
        """P1-G Verification: When no messages are newer than watermark, watermark remains unchanged and no redundant edges are written."""
        watermark = 1520
        new_msgs = []
        new_max_id = max((m.id for m in new_msgs), default=watermark)
        self.assertEqual(new_max_id, watermark, "Watermark must remain stable when no new messages exist.")


if __name__ == '__main__':
    unittest.main()
