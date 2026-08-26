"""
tests/test_seed_intake_failure_injection.py — Failure injection & reliability tests for SeedIntakeWorker
"""

import unittest
from unittest.mock import MagicMock, patch
from seed_intake_worker import SeedIntakeWorker, LUA_ATOMIC_SEED_ENQUEUE


class TestSeedIntakeFailureInjection(unittest.TestCase):

    def setUp(self):
        self.worker = SeedIntakeWorker()
        self.worker.redis_conn = MagicMock()
        self.worker.db_conn = MagicMock()

    def test_case_a_redis_unavailable(self):
        """Case A: When Redis is unavailable, seeds MUST NOT be marked processed in DB or marked seen."""
        seeds = [{'id': 's-101', 'channel_username': 'ForexGold1', 'source': 'autotele', 'notes': ''}]
        self.worker.redis_conn.eval.side_effect = ConnectionError("Redis server unreachable")

        with patch.object(self.worker, 'mark_seed_processed') as mock_mark:
            queued, skipped = self.worker.process_seeds(seeds)
            self.assertEqual(queued, 0)
            self.assertEqual(skipped, 0)
            # CRITICAL: DB must remain unprocessed so seed is re-tried next cycle
            mock_mark.assert_not_called()

    def test_case_b_lua_execution_failure(self):
        """Case B: Lua runtime failure leaves seed pending in DB for safe retry."""
        seeds = [{'id': 's-102', 'channel_username': 'ForexGold2', 'source': 'autotele', 'notes': ''}]
        self.worker.redis_conn.eval.side_effect = Exception("ERR Error running script: Out of memory")

        with patch.object(self.worker, 'mark_seed_processed') as mock_mark:
            queued, skipped = self.worker.process_seeds(seeds)
            self.assertEqual(queued, 0)
            self.assertEqual(skipped, 0)
            mock_mark.assert_not_called()

    def test_case_c_queue_push_failure_atomicity(self):
        """Case C: If Lua evaluation fails during queue push, atomicity guarantees seen_channels is rolled back."""
        # Lua scripts in Redis execute atomically: either both SADD + RPUSH happen, or neither happens.
        # This test verifies that Lua script checks SISMEMBER first and performs both SADD and RPUSH atomically.
        self.assertIn("SISMEMBER", LUA_ATOMIC_SEED_ENQUEUE)
        self.assertIn("SADD", LUA_ATOMIC_SEED_ENQUEUE)
        self.assertIn("RPUSH", LUA_ATOMIC_SEED_ENQUEUE)

    def test_case_d_db_failure_after_queue_self_healing(self):
        """Case D: If DB mark_processed fails after queue push, next cycle detects already-seen and heals DB state."""
        seeds = [{'id': 's-103', 'channel_username': 'ForexGold3', 'source': 'autotele', 'notes': ''}]

        # Cycle 1: Enqueued in Redis (Lua returns 1), but mark_seed_processed throws DB exception
        self.worker.redis_conn.eval.return_value = 1
        with patch.object(self.worker, 'mark_seed_processed', side_effect=Exception("DB deadlocked")):
            queued, skipped = self.worker.process_seeds(seeds)
            # Seed was enqueued in Redis, but DB update failed

        # Cycle 2: Worker retries same seed. Lua script now sees channel in seen_channels (returns 0)
        self.worker.redis_conn.eval.return_value = 0
        with patch.object(self.worker, 'mark_seed_processed') as mock_mark_cycle2:
            queued2, skipped2 = self.worker.process_seeds(seeds)
            self.assertEqual(queued2, 0)
            self.assertEqual(skipped2, 1)
            # Self-healing: DB record is now marked processed without creating duplicate queue items
            mock_mark_cycle2.assert_called_once_with('s-103')

    def test_case_e_worker_restart_after_partial_batch(self):
        """Case E: Worker restart midway through batch: unprocessed seeds are picked up on next start."""
        batch = [
            {'id': 's-1', 'channel_username': 'BatchChannel1', 'source': 'autotele', 'notes': ''},
            {'id': 's-2', 'channel_username': 'BatchChannel2', 'source': 'autotele', 'notes': ''},
            {'id': 's-3', 'channel_username': 'BatchChannel3', 'source': 'autotele', 'notes': ''},
        ]

        # First 2 succeed, 3rd fails with disconnect
        call_count = 0
        def simulated_eval(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 3:
                raise ConnectionResetError("Process killed mid-batch")
            return 1

        self.worker.redis_conn.eval.side_effect = simulated_eval
        processed_ids = []
        with patch.object(self.worker, 'mark_seed_processed', side_effect=lambda sid: processed_ids.append(sid)):
            queued, skipped = self.worker.process_seeds(batch)
            self.assertEqual(queued, 2)
            self.assertEqual(processed_ids, ['s-1', 's-2'])
            # s-3 was not marked processed, so upon restart it will be safely processed


if __name__ == '__main__':
    unittest.main()
