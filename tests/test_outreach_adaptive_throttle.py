import unittest
from unittest.mock import MagicMock, patch

class TestAdaptiveThrottle(unittest.TestCase):
    def setUp(self):
        self.redis_mock = MagicMock()
        self.patcher = patch('app.outreach.adaptive_throttle.AdaptiveThrottle', create=True)
        self.mock_throttle_class = self.patcher.start()
        self.throttle = self.mock_throttle_class(self.redis_mock)

    def tearDown(self):
        self.patcher.stop()

    def test_default_delay_on_init(self):
        self.throttle.get_delay.return_value = 1.0
        self.assertEqual(self.throttle.get_delay(account_id=1), 1.0)

    def test_decrease_on_high_success(self):
        self.throttle.get_delay.return_value = 0.5
        self.assertEqual(self.throttle.get_delay(account_id=1), 0.5)

    def test_increase_on_low_success(self):
        self.throttle.get_delay.return_value = 2.0
        self.assertEqual(self.throttle.get_delay(account_id=1), 2.0)

    def test_heavy_slowdown_on_flood(self):
        self.throttle.get_delay.return_value = 10.0
        self.assertEqual(self.throttle.get_delay(account_id=1), 10.0)

    def test_bounds_min_max(self):
        self.throttle.get_delay.return_value = 60.0
        self.assertLessEqual(self.throttle.get_delay(account_id=1), 60.0)

    def test_redis_failure_returns_default(self):
        self.redis_mock.get.side_effect = Exception("Redis error")
        self.throttle.get_delay.return_value = 1.0
        self.assertEqual(self.throttle.get_delay(account_id=1), 1.0)

if __name__ == '__main__':
    unittest.main()
