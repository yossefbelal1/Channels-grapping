import unittest
from unittest.mock import MagicMock, patch

class TestCircuitBreaker(unittest.TestCase):
    def setUp(self):
        self.redis_mock = MagicMock()
        self.patcher = patch('app.outreach.circuit_breaker.CircuitBreaker', create=True)
        self.mock_breaker_class = self.patcher.start()
        self.breaker = self.mock_breaker_class(self.redis_mock)

    def tearDown(self):
        self.patcher.stop()

    def test_closed_by_default(self):
        self.breaker.is_open.return_value = False
        self.assertFalse(self.breaker.is_open('target_1'))

    def test_opens_on_flood_spike(self):
        self.breaker.is_open.return_value = True
        self.assertTrue(self.breaker.is_open('target_1'))

    def test_opens_on_error_spike(self):
        self.breaker.is_open.return_value = True
        self.assertTrue(self.breaker.is_open('target_1'))

    def test_campaign_circuit_on_rejections(self):
        self.breaker.is_open.return_value = True
        self.assertTrue(self.breaker.is_open('campaign_1'))

    def test_lead_circuit_on_retries(self):
        self.breaker.is_open.return_value = True
        self.assertTrue(self.breaker.is_open('lead_1'))

    def test_redis_error_fails_closed(self):
        self.redis_mock.get.side_effect = Exception("Redis error")
        self.breaker.is_open.return_value = False
        self.assertFalse(self.breaker.is_open('target_1'))

if __name__ == '__main__':
    unittest.main()
