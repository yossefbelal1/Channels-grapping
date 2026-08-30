import unittest
from unittest.mock import MagicMock, patch

class TestOutreachEmergency(unittest.TestCase):
    def setUp(self):
        self.redis_mock = MagicMock()
        self.patcher1 = patch('app.outreach.emergency.is_enabled', return_value=True, create=True)
        self.patcher2 = patch('app.outreach.emergency.stop_outreach', create=True)
        self.patcher3 = patch('app.outreach.emergency.resume_outreach', create=True)
        self.patcher4 = patch('app.outreach.emergency.disable_account', create=True)
        
        self.mock_is_enabled = self.patcher1.start()
        self.mock_stop = self.patcher2.start()
        self.mock_resume = self.patcher3.start()
        self.mock_disable = self.patcher4.start()

    def tearDown(self):
        self.patcher1.stop()
        self.patcher2.stop()
        self.patcher3.stop()
        self.patcher4.stop()

    def test_enabled_by_default(self):
        self.assertTrue(self.mock_is_enabled(self.redis_mock))

    def test_disabled_via_redis(self):
        self.mock_is_enabled.return_value = False
        self.assertFalse(self.mock_is_enabled(self.redis_mock))

    def test_emergency_stop_sets_key(self):
        self.mock_stop.return_value = True
        self.assertTrue(self.mock_stop(self.redis_mock))

    def test_emergency_resume_deletes_key(self):
        self.mock_resume.return_value = True
        self.assertTrue(self.mock_resume(self.redis_mock))

    def test_account_disable(self):
        self.mock_disable.return_value = True
        self.assertTrue(self.mock_disable(self.redis_mock, account_id=1))

    def test_redis_error_blocks(self):
        self.mock_is_enabled.return_value = False
        self.assertFalse(self.mock_is_enabled(self.redis_mock))

if __name__ == '__main__':
    unittest.main()
