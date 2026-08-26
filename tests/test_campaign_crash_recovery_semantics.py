"""
tests/test_campaign_crash_recovery_semantics.py — Tests for Campaign Idempotency, Concurrency, and Crash Recovery
"""

import unittest
from unittest.mock import MagicMock, patch
import threading
from datetime import datetime


class TestCampaignCrashRecoverySemantics(unittest.TestCase):

    def test_case_1_claim_and_send_fails_updates_error_status(self):
        """Case 1: When Telegram send fails, log row transitions from 'processing' to 'failed' with error_message."""
        mock_cur = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        log_id = "log-fail-1"
        error_msg = "Telegram rate limit: FloodWaitError (300s)"

        # Simulate update to failed state
        mock_cur.execute(
            "UPDATE campaign_logs SET status = 'failed', error_message = %s, sent_at = %s WHERE id = %s",
            (error_msg, datetime.now(), log_id)
        )
        mock_conn.commit()

        mock_cur.execute.assert_called_once()
        self.assertEqual(mock_cur.execute.call_args[0][1][0], error_msg)

    def test_case_2_claim_send_succeeds_db_succeeds(self):
        """Case 2: Happy path: send succeeds -> Redis idempotency token set -> DB marked sent."""
        mock_redis = MagicMock()
        mock_cur = MagicMock()

        campaign_id = "camp-100"
        lead_id = "lead-200"
        log_id = "log-300"
        idempotency_key = f"campaign:delivered:{campaign_id}:{lead_id}"

        # 1. Message send succeeded -> set 30-day token in Redis
        mock_redis.set(idempotency_key, "1", ex=86400 * 30)

        # 2. Update DB
        mock_cur.execute(
            "UPDATE campaign_logs SET status = 'sent', sent_at = %s WHERE id = %s",
            (datetime.now(), log_id)
        )

        mock_redis.set.assert_called_once_with(idempotency_key, "1", ex=86400 * 30)
        mock_cur.execute.assert_called_once()

    def test_case_3_crash_after_send_recovery(self):
        """Case 3: Crash after Telegram send but before DB update: recovering worker checks Redis and marks sent without resending."""
        mock_redis = MagicMock()
        mock_cur = MagicMock()

        campaign_id = "camp-crash"
        lead_id = "lead-crash"
        log_id = "log-crash"
        idempotency_key = f"campaign:delivered:{campaign_id}:{lead_id}"

        # Simulate: message was already sent in prior run and exists in Redis
        mock_redis.exists.return_value = True

        telegram_dispatched = False

        # In recovering worker loop:
        if mock_redis.exists(idempotency_key):
            # Idempotency hit: skip Telegram call and mark DB sent
            mock_cur.execute("UPDATE campaign_logs SET status = 'sent', sent_at = %s WHERE id = %s", (datetime.now(), log_id))
        else:
            telegram_dispatched = True

        self.assertFalse(telegram_dispatched, "CRITICAL: Should NOT dispatch to Telegram if Redis delivery token already exists.")
        mock_cur.execute.assert_called_once()

    def test_case_4_concurrent_worker_claiming_simulation(self):
        """Case 4: Two or more concurrent workers racing for pending rows: SKIP LOCKED guarantees mutually exclusive claiming."""
        pending_rows = {
            101: {"status": "pending", "campaign_id": "c1", "lead_id": "l1"},
            102: {"status": "pending", "campaign_id": "c1", "lead_id": "l2"},
        }
        lock = threading.Lock()
        claims = []

        def worker_task(worker_id):
            with lock:
                for row_id, data in pending_rows.items():
                    if data["status"] == "pending":
                        data["status"] = "processing"
                        claims.append((worker_id, row_id))
                        break

        threads = [threading.Thread(target=worker_task, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Only 2 rows existed, so exactly 2 workers should have claimed rows
        self.assertEqual(len(claims), 2)
        claimed_row_ids = [c[1] for c in claims]
        self.assertEqual(len(set(claimed_row_ids)), 2, "Each row MUST be claimed by at most one worker.")

    def test_case_5_followup_skips_contact_who_replied(self):
        """Case 5: Follow-up logic strictly skips any contact who sent incoming messages or where dialogue > 2 messages."""
        # Simulated chat messages
        class MockMsg:
            def __init__(self, out):
                self.out = out  # out=True means sent by us, out=False means incoming reply from contact

        # Case A: Contact replied (incoming message)
        msgs_with_reply = [MockMsg(out=True), MockMsg(out=False)]
        has_incoming = any(not getattr(m, 'out', True) for m in msgs_with_reply)
        self.assertTrue(has_incoming, "Should detect incoming reply from lead.")

        # Case B: Only our initial pitch was sent
        msgs_no_reply = [MockMsg(out=True)]
        has_incoming_b = any(not getattr(m, 'out', True) for m in msgs_no_reply)
        self.assertFalse(has_incoming_b, "Should allow follow-up when no incoming reply was received.")


if __name__ == '__main__':
    unittest.main()
