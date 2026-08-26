"""
tests/test_seed_intake_regression.py — Tests for Seed Queue Reliability & Crash-Safety
"""

import unittest
from unittest.mock import MagicMock, patch
from seed_intake_worker import SeedIntakeWorker, LUA_ATOMIC_SEED_ENQUEUE


class TestSeedIntakeRegression(unittest.TestCase):

    def setUp(self):
        self.worker = SeedIntakeWorker()
        self.worker.redis_conn = MagicMock()
        self.worker.db_conn = MagicMock()

    def test_atomic_lua_enqueue_structure(self):
        """Verify Lua script checks SISMEMBER before adding to seen_channels and queue."""
        self.assertIn("SISMEMBER", LUA_ATOMIC_SEED_ENQUEUE)
        self.assertIn("SADD", LUA_ATOMIC_SEED_ENQUEUE)
        self.assertIn("RPUSH", LUA_ATOMIC_SEED_ENQUEUE)

    def test_seed_marked_processed_only_when_enqueued(self):
        """Ensure seed is marked processed in DB when Lua script returns 1 (enqueued)."""
        seeds = [{
            'id': 'seed-123',
            'channel_username': 'ForexGoldChannel',
            'source': 'autotele',
            'notes': 'Test seed'
        }]
        # Mock Lua script returning 1 (successfully enqueued)
        self.worker.redis_conn.eval.return_value = 1
        with patch.object(self.worker, 'mark_seed_processed') as mock_mark:
            queued, skipped = self.worker.process_seeds(seeds)
            self.assertEqual(queued, 1)
            self.assertEqual(skipped, 0)
            mock_mark.assert_called_once_with('seed-123')

    def test_seed_skipped_if_already_known(self):
        """Ensure seed is marked processed and skipped if Lua script returns 0 (already in seen_channels)."""
        seeds = [{
            'id': 'seed-456',
            'channel_username': 'KnownChannel',
            'source': 'autotele',
            'notes': 'Test seed'
        }]
        # Mock Lua script returning 0 (already known)
        self.worker.redis_conn.eval.return_value = 0
        with patch.object(self.worker, 'mark_seed_processed') as mock_mark:
            queued, skipped = self.worker.process_seeds(seeds)
            self.assertEqual(queued, 0)
            self.assertEqual(skipped, 1)
            mock_mark.assert_called_once_with('seed-456')

    def test_seed_not_lost_when_redis_fails(self):
        """P0 Regression: Ensure seed is NOT marked processed and NOT marked seen if Redis throws an exception."""
        seeds = [{
            'id': 'seed-789',
            'channel_username': 'FailedChannel',
            'source': 'autotele',
            'notes': 'Test seed'
        }]
        # Mock Redis failing during enqueue
        self.worker.redis_conn.eval.side_effect = Exception("Redis connection lost")
        with patch.object(self.worker, 'mark_seed_processed') as mock_mark:
            queued, skipped = self.worker.process_seeds(seeds)
            self.assertEqual(queued, 0)
            self.assertEqual(skipped, 0)
            # Crucial: mark_seed_processed MUST NOT be called so it stays pending for next cycle
            mock_mark.assert_not_called()


if __name__ == '__main__':
    unittest.main()
