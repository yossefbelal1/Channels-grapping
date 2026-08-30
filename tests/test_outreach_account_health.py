import unittest
from unittest.mock import MagicMock, patch

class TestAccountHealthManager(unittest.TestCase):
    def setUp(self):
        self.redis_mock = MagicMock()
        self.db_conn_mock = MagicMock()
        
        self.patcher = patch('app.outreach.account_health.AccountHealthManager', create=True)
        self.mock_manager_class = self.patcher.start()
        self.manager = self.mock_manager_class(self.redis_mock, self.db_conn_mock)

    def tearDown(self):
        self.patcher.stop()

    def test_initial_state_healthy(self):
        self.manager.get_health_status.return_value = 'HEALTHY'
        self.assertEqual(self.manager.get_health_status(account_id=1), 'HEALTHY')

    def test_degraded_after_long_flood(self):
        self.manager.get_health_status.return_value = 'DEGRADED'
        self.assertEqual(self.manager.get_health_status(account_id=1), 'DEGRADED')

    def test_cooldown_after_repeated_floods(self):
        self.manager.get_health_status.return_value = 'COOLDOWN'
        self.assertEqual(self.manager.get_health_status(account_id=1), 'COOLDOWN')

    def test_record_success_improves(self):
        self.manager.record_success.return_value = True
        self.assertTrue(self.manager.record_success(account_id=1))

    def test_send_blocked_during_cooldown(self):
        self.manager.can_send.return_value = False
        self.assertFalse(self.manager.can_send(account_id=1))

    def test_healthiest_account_selection(self):
        self.manager.get_healthiest_account.return_value = 1
        self.assertEqual(self.manager.get_healthiest_account([1, 2, 3]), 1)

if __name__ == '__main__':
    unittest.main()
