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

    def test_direct_emergency_stop_and_resume(self):
        from app.outreach.emergency import emergency_stop, emergency_resume, is_kill_switch_active, is_outreach_enabled
        
        real_redis_state = {}
        mock_r = MagicMock()
        def mock_set(k, v): real_redis_state[k] = str(v)
        def mock_del(k): real_redis_state.pop(k, None)
        def mock_get(k): return real_redis_state.get(k)
        
        mock_r.set.side_effect = mock_set
        mock_r.delete.side_effect = mock_del
        mock_r.get.side_effect = mock_get
        
        # Test emergency_stop
        emergency_stop(mock_r)
        self.assertEqual(real_redis_state.get("outreach:global:enabled"), "0")
        self.assertEqual(real_redis_state.get("outreach:emergency_stop"), "1")
        killed, _ = is_kill_switch_active(mock_r)
        self.assertTrue(killed)
        
        # Test emergency_resume
        emergency_resume(mock_r)
        self.assertNotIn("outreach:emergency_stop", real_redis_state)
        self.assertEqual(real_redis_state.get("outreach:global:enabled"), "1")
        killed_after, _ = is_kill_switch_active(mock_r)
        self.assertFalse(killed_after)

if __name__ == '__main__':
    unittest.main()

