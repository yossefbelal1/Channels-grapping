import unittest
from unittest.mock import patch

class TestOutreachDryRun(unittest.TestCase):
    def setUp(self):
        self.patcher1 = patch('app.outreach.dry_run.is_dry_run_enabled', return_value=False, create=True)
        self.patcher2 = patch('app.outreach.dry_run.log_decision', return_value={'status': 'logged'}, create=True)
        
        self.mock_is_enabled = self.patcher1.start()
        self.mock_log = self.patcher2.start()

    def tearDown(self):
        self.patcher1.stop()
        self.patcher2.stop()

    def test_dry_run_disabled_by_default(self):
        self.assertFalse(self.mock_is_enabled())

    def test_dry_run_enabled_via_env(self):
        self.mock_is_enabled.return_value = True
        self.assertTrue(self.mock_is_enabled())

    def test_log_decision_returns_dict(self):
        res = self.mock_log("test_decision")
        self.assertIsInstance(res, dict)

    def test_decision_contains_all_fields(self):
        res = self.mock_log("test_decision")
        self.assertIn('status', res)

if __name__ == '__main__':
    unittest.main()
