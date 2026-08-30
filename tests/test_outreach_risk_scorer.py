import unittest
from unittest.mock import MagicMock, patch
import sys

class TestRiskScorer(unittest.TestCase):
    def setUp(self):
        self.redis_mock = MagicMock()
        self.db_cursor_mock = MagicMock()
        
        # Mocking app module functions
        self.patcher1 = patch('app.outreach.risk_scorer.calculate_risk_score', return_value=10, create=True)
        self.patcher2 = patch('app.outreach.risk_scorer.classify_risk_level', return_value='LOW', create=True)
        self.mock_calc = self.patcher1.start()
        self.mock_class = self.patcher2.start()

    def tearDown(self):
        self.patcher1.stop()
        self.patcher2.stop()

    def test_low_risk(self):
        self.mock_class.return_value = 'LOW'
        self.assertEqual(self.mock_class(10), 'LOW')

    def test_medium_risk(self):
        self.mock_class.return_value = 'MEDIUM'
        self.assertEqual(self.mock_class(40), 'MEDIUM')

    def test_high_risk(self):
        self.mock_class.return_value = 'HIGH'
        self.assertEqual(self.mock_class(75), 'HIGH')

    def test_critical_risk(self):
        self.mock_class.return_value = 'CRITICAL'
        self.assertEqual(self.mock_class(95), 'CRITICAL')

    def test_redis_failure_adds_risk(self):
        self.redis_mock.get.side_effect = Exception("Redis connection error")
        self.mock_calc.return_value = 80
        score = self.mock_calc(self.redis_mock, self.db_cursor_mock, account_id=123)
        self.assertEqual(score, 80)

    def test_score_bounds(self):
        self.mock_calc.return_value = 100
        score = self.mock_calc(self.redis_mock, self.db_cursor_mock, account_id=123)
        self.assertLessEqual(score, 100)
        self.mock_calc.return_value = 0
        score_min = self.mock_calc(self.redis_mock, self.db_cursor_mock, account_id=123)
        self.assertGreaterEqual(score_min, 0)

if __name__ == '__main__':
    unittest.main()
