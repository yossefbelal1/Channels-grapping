import unittest
from unittest.mock import MagicMock, patch

class TestOutreachEligibility(unittest.TestCase):
    def setUp(self):
        self.redis_mock = MagicMock()
        self.db_cursor_mock = MagicMock()
        self.patcher = patch('app.outreach.eligibility.check_eligibility', create=True)
        self.mock_check = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_eligible_valid_lead(self):
        self.mock_check.return_value = "ELIGIBLE"
        self.assertEqual(self.mock_check(self.redis_mock, self.db_cursor_mock, lead_id=1), "ELIGIBLE")

    def test_blocked_no_contact(self):
        self.mock_check.return_value = "BLOCKED_NO_CONTACT"
        self.assertEqual(self.mock_check(self.redis_mock, self.db_cursor_mock, lead_id=2), "BLOCKED_NO_CONTACT")

    def test_blocked_is_bot(self):
        self.mock_check.return_value = "BLOCKED_IS_BOT"
        self.assertEqual(self.mock_check(self.redis_mock, self.db_cursor_mock, lead_id=3), "BLOCKED_IS_BOT")

    def test_blocked_blacklisted(self):
        self.mock_check.return_value = "BLOCKED_BLACKLISTED"
        self.assertEqual(self.mock_check(self.redis_mock, self.db_cursor_mock, lead_id=4), "BLOCKED_BLACKLISTED")

    def test_contacted_already_sent(self):
        self.mock_check.return_value = "ALREADY_SENT"
        self.assertEqual(self.mock_check(self.redis_mock, self.db_cursor_mock, lead_id=5), "ALREADY_SENT")

    def test_cooldown_recent_contact(self):
        self.mock_check.return_value = "COOLDOWN"
        self.assertEqual(self.mock_check(self.redis_mock, self.db_cursor_mock, lead_id=6), "COOLDOWN")

    def test_failed_permanent_history(self):
        self.mock_check.return_value = "FAILED_PERMANENT"
        self.assertEqual(self.mock_check(self.redis_mock, self.db_cursor_mock, lead_id=7), "FAILED_PERMANENT")

if __name__ == '__main__':
    unittest.main()
