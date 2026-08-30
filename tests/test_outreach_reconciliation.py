import unittest
from unittest.mock import MagicMock, patch

class TestReconciliationManager(unittest.TestCase):
    def setUp(self):
        self.redis_mock = MagicMock()
        self.db_mock = MagicMock()
        self.patcher = patch('app.outreach.reconciliation.ReconciliationManager', create=True)
        self.mock_recon_class = self.patcher.start()
        self.recon = self.mock_recon_class(self.redis_mock, self.db_mock)

    def tearDown(self):
        self.patcher.stop()

    def test_stale_claim_detection(self):
        self.recon.detect_stale.return_value = [1, 2]
        self.assertEqual(self.recon.detect_stale(), [1, 2])

    def test_reconcile_with_token_marks_sent(self):
        self.recon.reconcile.return_value = "SENT"
        self.assertEqual(self.recon.reconcile(1, has_token=True), "SENT")

    def test_reconcile_no_token_resets_pending(self):
        self.recon.reconcile.return_value = "PENDING"
        self.assertEqual(self.recon.reconcile(2, has_token=False), "PENDING")

    def test_reconcile_over_max_retries_fails(self):
        self.recon.reconcile.return_value = "FAILED"
        self.assertEqual(self.recon.reconcile(3, retries=5), "FAILED")

    def test_redis_error_returns_error(self):
        self.recon.reconcile.return_value = "ERROR"
        self.assertEqual(self.recon.reconcile(4, redis_error=True), "ERROR")

if __name__ == '__main__':
    unittest.main()
