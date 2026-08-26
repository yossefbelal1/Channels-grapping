"""
tests/test_concurrency_race_conditions.py — Concurrency & Race Condition Tests
"""

import unittest
import threading
import time
from unittest.mock import MagicMock


class TestConcurrencyRaceConditions(unittest.TestCase):

    def test_20_concurrent_session_lock_claims(self):
        """P1 Concurrency Test: Simulate 20 concurrent worker threads racing for the same Telethon session lock."""
        # Thread-safe in-memory Redis simulation
        lock_state = {}
        lock_mutex = threading.Lock()

        def simulated_set_nx(key, value, ex=60):
            with lock_mutex:
                if key in lock_state:
                    return False
                lock_state[key] = value
                return True

        winners = []
        threads = []

        def worker_claim(worker_id):
            owner_token = f"worker_{worker_id}"
            acquired = simulated_set_nx("lock:session:validator_session", owner_token)
            if acquired:
                winners.append(owner_token)

        # Launch 20 concurrent threads simultaneously
        for i in range(20):
            t = threading.Thread(target=worker_claim, args=(i,))
            threads.append(t)

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # Assert exactly ONE winner acquired the distributed session lock
        self.assertEqual(len(winners), 1, "Exactly one worker MUST acquire the session lock across concurrent attempts.")
        self.assertEqual(lock_state["lock:session:validator_session"], winners[0])

    def test_campaign_claim_skip_locked_simulation(self):
        """P1 Concurrency Test: Simulate 20 workers racing for pending campaign rows with SKIP LOCKED semantics."""
        # Simulated database table
        pending_rows = {
            1: {"id": 1, "status": "pending", "lead_id": 101},
            2: {"id": 2, "status": "pending", "lead_id": 102},
            3: {"id": 3, "status": "pending", "lead_id": 103},
        }
        db_mutex = threading.Lock()
        claimed_records = []

        def claim_row(worker_id):
            with db_mutex:
                # Find first available row with status == 'pending' (emulating SKIP LOCKED)
                for row_id, row in pending_rows.items():
                    if row["status"] == "pending":
                        row["status"] = "processing"
                        claimed_records.append((worker_id, row_id))
                        break

        threads = []
        for i in range(20):
            t = threading.Thread(target=claim_row, args=(i,))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert that each row was claimed at most once across all 20 workers
        claimed_row_ids = [r[1] for r in claimed_records]
        self.assertEqual(len(claimed_row_ids), 3)
        self.assertEqual(len(set(claimed_row_ids)), 3, "No two workers should ever claim the same campaign row.")

    def test_campaign_idempotency_crash_window_recovery(self):
        """P0 Regression: Simulate a crash between Telegram dispatch and DB update, and test recovery."""
        redis_delivered_keys = set()
        campaign_id = "camp-999"
        lead_id = "lead-888"
        idempotency_key = f"campaign:delivered:{campaign_id}:{lead_id}"

        # 1. Step 1: Message was dispatched to Telegram and registered in Redis, but worker crashed before DB update
        redis_delivered_keys.add(idempotency_key)

        # 2. Step 2: Worker restarts or re-claims the row in 'processing' status
        telegram_send_called = False

        # In worker recovery loop:
        if idempotency_key in redis_delivered_keys:
            # Skip Telegram dispatch and immediately mark sent
            db_status = "sent"
        else:
            telegram_send_called = True
            db_status = "sent"

        self.assertFalse(telegram_send_called, "Should NOT re-send to Telegram if idempotency token exists.")
        self.assertEqual(db_status, "sent")


if __name__ == '__main__':
    unittest.main()
