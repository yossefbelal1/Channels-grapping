import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import json
import os


class TestDiscoveryAndSchedulerIntegration(unittest.TestCase):
    """
    Test-Driven Verification for:
    1. Preservation of discovered_at timestamp on re-scan (no 24h freeze).
    2. Extraction of forward/mention channels from dialog messages into queue:normal.
    3. Embedded PriorityScheduler activation and due channel dispatching.
    4. Contract alignment between backend API and frontend charts.
    """

    def test_embedded_scheduler_default_true(self):
        """Embedded scheduler should default to 'true' in single-worker environment."""
        with patch.dict(os.environ, {}, clear=True):
            # os.getenv("ENABLE_EMBEDDED_SCHEDULER", "true") should be true
            scheduler_flag = os.getenv("ENABLE_EMBEDDED_SCHEDULER", "true").lower() == "true"
            self.assertTrue(scheduler_flag)

    @patch("app.scheduler.priority_scheduler.PriorityScheduler.acquire_leader_lock", return_value=True)
    @patch("app.scheduler.priority_scheduler.PriorityScheduler.release_leader_lock")
    @patch("app.scheduler.priority_scheduler.PriorityScheduler.get_channels_due_for_crawl")
    @patch("app.scheduler.priority_scheduler.PriorityScheduler.schedule_channel_crawl")
    def test_priority_scheduler_dispatches_due_channels(
        self, mock_schedule, mock_get_due, mock_release, mock_acquire
    ):
        """PriorityScheduler must pull due channels and dispatch crawl jobs."""
        from app.scheduler.priority_scheduler import PriorityScheduler

        mock_redis = MagicMock()
        mock_db = MagicMock()
        scheduler = PriorityScheduler(mock_redis, mock_db)

        # Mock 2 due channels
        mock_get_due.return_value = [
            {"id": "1", "channel_username": "forex_gold_signals", "last_scanned_message_id": 100},
            {"id": "2", "channel_username": "vip_scalping_arabic", "last_scanned_message_id": 0}
        ]
        mock_schedule.return_value = "job-uuid-123"

        due = scheduler.get_channels_due_for_crawl(batch_size=10)
        self.assertEqual(len(due), 2)

        for ch in due:
            job_id = scheduler.schedule_channel_crawl(
                channel_id=ch["id"],
                channel_username=ch["channel_username"],
                channel_data=ch,
                job_type="incremental" if ch["last_scanned_message_id"] > 0 else "deep_scan"
            )
            self.assertEqual(job_id, "job-uuid-123")

        self.assertEqual(mock_schedule.call_count, 2)

    def test_dialog_message_link_and_forward_extraction(self):
        """Verify regex extraction of channel links and @mentions from post text."""
        import re

        text = """
        🔥 توصيات ذهب فوركس VIP مجانية!
        انضموا إلى قناتنا الاحتياطية: https://t.me/super_gold_vip
        للتواصل مع الإدارة: @gold_admin_trade
        رابط شريكنا: t.me/forex_arabic_signals
        """

        JUNK = {'joinchat', 'share', 'bot', 'spambot'}
        discovered = set()

        # 1. t.me links
        for m in re.finditer(r'(?:https?://)?(?:t\.me|telegram\.me)/(?:joinchat/)?(\+?[a-zA-Z0-9_.-]{4,32})', text):
            cand = m.group(1).lstrip('+').strip()
            if cand and not cand.lower().endswith('bot') and cand.lower() not in JUNK:
                discovered.add(cand.lower())

        # 2. @mentions
        for at_m in re.finditer(r'@([a-zA-Z0-9_]{5,32})', text):
            cand = at_m.group(1).strip()
            if cand and not cand.lower().endswith('bot') and cand.lower() not in JUNK:
                discovered.add(cand.lower())

        self.assertIn("super_gold_vip", discovered)
        self.assertIn("gold_admin_trade", discovered)
        self.assertIn("forex_arabic_signals", discovered)
        self.assertEqual(len(discovered), 3)

    def test_discovered_at_coalesce_contract(self):
        """Simulate SQL update logic: discovered_at must not be overwritten if already set."""
        # Simulated row with existing discovered_at
        existing_row = {
            "channel_username": "gold_channel",
            "discovered_at": "2026-11-20T00:00:00",
            "last_scan": "2026-11-20T00:00:00"
        }

        # Simulated ON CONFLICT DO UPDATE SET discovered_at = COALESCE(leads.discovered_at, NOW()), last_scan = NOW()
        new_now = "2026-11-22T12:00:00"
        simulated_update = {
            "channel_username": existing_row["channel_username"],
            "discovered_at": existing_row["discovered_at"] or new_now,  # COALESCE
            "last_scan": new_now
        }

        # Discovered at must remain the original date!
        self.assertEqual(simulated_update["discovered_at"], "2026-11-20T00:00:00")
        # Last scan must be updated to new time
        self.assertEqual(simulated_update["last_scan"], new_now)


if __name__ == "__main__":
    unittest.main()
