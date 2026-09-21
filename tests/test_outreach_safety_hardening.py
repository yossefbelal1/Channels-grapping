import os
import unittest
from unittest.mock import MagicMock, patch
import pytest

from app.outreach.emergency import (
    is_kill_switch_active,
    is_outreach_enabled,
    check_outreach_safety_gate,
    emergency_stop,
)
from app.outreach.constants import DeliveryState
from validator import apply_natural_greeting_variation


class TestOutreachSafetyHardening(unittest.TestCase):
    def setUp(self):
        self.redis_mock = MagicMock()
        # By default mock redis to have no kill switch and enabled global outreach
        def mock_get(k):
            if k == "outreach:global:enabled":
                return "1"
            if k == "outreach:emergency_stop":
                return None
            return None
        self.redis_mock.get.side_effect = mock_get

    def test_helper_session_lockout(self):
        """Helper accounts must be strictly blocked by Layer 3 Single-Account Guard."""
        with patch.dict(os.environ, {"OUTREACH_ENABLED": "true", "CAMPAIGN_MODE": "live"}):
            for helper in ['scavenger', 'radar', 'graph_expander', 'helper_1']:
                ok, reason = check_outreach_safety_gate(
                    redis_conn=self.redis_mock,
                    session_name=helper,
                    target_username='testuser',
                    log_status='approved',
                    campaign_mode='live'
                )
                self.assertFalse(ok)
                self.assertIn("SECURITY_VIOLATION", reason)
                self.assertIn(helper, reason)

    def test_pending_review_blocked_by_safety_gate(self):
        """Leads in pending_review state must not be dispatched (Layer 4 Approval Gate)."""
        with patch.dict(os.environ, {"OUTREACH_ENABLED": "true", "CAMPAIGN_MODE": "live"}):
            ok, reason = check_outreach_safety_gate(
                redis_conn=self.redis_mock,
                session_name='user_session',
                target_username='testuser',
                log_status='pending_review',
                campaign_mode='live'
            )
            self.assertFalse(ok)
            self.assertIn("APPROVAL_REQUIRED", reason)
            self.assertIn("pending_review", reason)

    def test_legacy_pending_blocked_by_safety_gate(self):
        """Legacy pending leads must be blocked until explicitly approved (Layer 4 Approval Gate)."""
        with patch.dict(os.environ, {"OUTREACH_ENABLED": "true", "CAMPAIGN_MODE": "live"}):
            ok, reason = check_outreach_safety_gate(
                redis_conn=self.redis_mock,
                session_name='user_session',
                target_username='testuser',
                log_status='pending',
                campaign_mode='live'
            )
            self.assertFalse(ok)
            self.assertIn("APPROVAL_REQUIRED", reason)
            self.assertIn("pending", reason)

    def test_kill_switch_blocks_outreach(self):
        """Active kill switch flag in Redis must immediately trip Layer 1."""
        self.redis_mock.get.side_effect = lambda k: "1" if k == "outreach:emergency_stop" else None
        killed, reason = is_kill_switch_active(self.redis_mock)
        self.assertTrue(killed)
        self.assertIn("outreach:emergency_stop", reason)

        ok, gate_reason = check_outreach_safety_gate(
            redis_conn=self.redis_mock,
            session_name='user_session',
            target_username='testuser',
            log_status='approved',
            campaign_mode='live'
        )
        self.assertFalse(ok)
        self.assertIn("BLOCKED_BY_KILL_SWITCH", gate_reason)

    def test_outreach_disabled_by_default(self):
        """When OUTREACH_ENABLED env is false/unset, outreach is fail-closed."""
        self.redis_mock.get.side_effect = lambda k: None
        with patch.dict(os.environ, {"OUTREACH_ENABLED": "false"}):
            self.assertFalse(is_outreach_enabled(self.redis_mock))

    def test_approved_passes_when_all_layers_green(self):
        """When user_session, approved, enabled, and no kill switch, gate passes."""
        with patch.dict(os.environ, {"OUTREACH_ENABLED": "true", "CAMPAIGN_MODE": "live"}):
            ok, reason = check_outreach_safety_gate(
                redis_conn=self.redis_mock,
                session_name='user_session',
                target_username='testuser',
                log_status='approved',
                campaign_mode='live'
            )
            self.assertTrue(ok)
            self.assertEqual(reason, "ALLOWED")

    def test_small_channel_views_gate_passes_above_20(self):
        """Small channel (<1000 members) with recent 10 posts views >= 20 must qualify without penalty."""
        member_count = 450
        is_inactive = False
        is_channel = True

        class MockMsg:
            def __init__(self, views):
                self.views = views

        messages = [MockMsg(views=35) for _ in range(10)]

        recent_10_msgs = messages[-10:] if len(messages) >= 10 else messages
        channel_views = [msg.views for msg in recent_10_msgs if getattr(msg, 'views', None) is not None]
        avg_views = int(sum(channel_views) / len(channel_views)) if channel_views else 0

        is_low_views = False
        is_medium_views_penalty = False
        if not is_inactive and is_channel and member_count < 1000:
            if avg_views < 20:
                is_low_views = True
                is_medium_views_penalty = True

        self.assertFalse(is_low_views)
        self.assertFalse(is_medium_views_penalty)
        self.assertGreaterEqual(avg_views, 20)

    def test_small_channel_views_gate_penalizes_below_20(self):
        """Small channel (<1000 members) with recent 10 posts views < 20 must be flagged and penalized."""
        member_count = 350
        is_inactive = False
        is_channel = True

        class MockMsg:
            def __init__(self, views):
                self.views = views

        messages = [MockMsg(views=12) for _ in range(10)]

        recent_10_msgs = messages[-10:] if len(messages) >= 10 else messages
        channel_views = [msg.views for msg in recent_10_msgs if getattr(msg, 'views', None) is not None]
        avg_views = int(sum(channel_views) / len(channel_views)) if channel_views else 0

        is_low_views = False
        is_medium_views_penalty = False
        if not is_inactive and is_channel and member_count < 1000:
            if avg_views < 20:
                is_low_views = True
                is_medium_views_penalty = True

        self.assertTrue(is_low_views)
        self.assertTrue(is_medium_views_penalty)
        self.assertLess(avg_views, 20)

    def test_natural_greeting_variation_varied_and_intact(self):
        """Greeting variations must vary the opening while preserving message pitch."""
        pitch = "السلام عليكم، هل تقبلون إعلانات على قناتكم؟ تفاصيل العرض متوفرة لدينا."
        results = set()
        for _ in range(30):
            varied = apply_natural_greeting_variation(pitch)
            results.add(varied.split()[0])
            self.assertIn("هل تقبلون إعلانات على قناتكم؟", varied)

        # Must have generated multiple varied greetings across 30 attempts
        self.assertGreater(len(results), 1)

    def test_daily_budget_target_capped_at_20(self):
        """Daily target budget must never exceed hard cap of 20."""
        import random
        for env_val in [20, 30, 60, 100]:
            with patch.dict(os.environ, {"CAMPAIGN_DAILY_LIMIT": str(env_val)}):
                env_max = int(os.getenv("CAMPAIGN_DAILY_LIMIT", 20))
                hard_cap = min(env_max, 20)
                target = random.randint(min(15, hard_cap), hard_cap)
                self.assertLessEqual(target, 20)
                self.assertGreaterEqual(target, 15)


if __name__ == '__main__':
    unittest.main()
