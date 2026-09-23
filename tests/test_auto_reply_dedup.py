"""
tests/test_auto_reply_dedup.py — Unit tests for AutoReplyEngine deduplication and concurrency safety
"""

import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from app.outreach.auto_reply import AutoReplyEngine


class TestAutoReplyDedup(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_client.is_connected.return_value = True
        self.mock_client.send_message = AsyncMock()
        self.mock_client.send_file = AsyncMock()
        self.mock_client.action = MagicMock()
        self.mock_client.get_me = AsyncMock(return_value=MagicMock(id=999999))
        self.mock_client.on.return_value = lambda fn: fn

        self.mock_redis = MagicMock()
        self.redis_store = {}

        def mock_redis_get(k):
            return self.redis_store.get(k)

        def mock_redis_set(k, v, nx=False, ex=None):
            if nx and k in self.redis_store:
                return False
            self.redis_store[k] = str(v)
            return True

        def mock_redis_delete(*keys):
            for k in keys:
                self.redis_store.pop(k, None)
            return 1

        self.mock_redis.get.side_effect = mock_redis_get
        self.mock_redis.set.side_effect = mock_redis_set
        self.mock_redis.delete.side_effect = mock_redis_delete

        self.mock_db = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_conn = MagicMock()
        self.mock_conn.cursor.return_value.__enter__.return_value = self.mock_cursor
        self.mock_db.conn = self.mock_conn
        self.shutdown_event = asyncio.Event()

        self.engine = AutoReplyEngine(
            user_client=self.mock_client,
            redis_conn=self.mock_redis,
            db_helper=self.mock_db,
            shutdown_event=self.shutdown_event
        )

    def test_post_sleep_dedup_aborts_if_dispatched_during_delay(self):
        """If another worker dispatches during the human delay, real-time handler must abort without sending."""
        async def run_test():
            self.engine.register_handler()
            handler = self.engine._registered_handler
            self.assertIsNotNone(handler)

            mock_event = MagicMock()
            mock_event.is_private = True
            mock_event.out = False
            mock_event.sender_id = 123456
            mock_event.chat_id = 123456
            mock_sender = MagicMock()
            mock_sender.bot = False
            mock_sender.username = "test_lead"
            mock_event.get_sender = AsyncMock(return_value=mock_sender)

            # DB returns matching campaign lead
            matched_row = {
                'log_id': 'log-uuid-123',
                'campaign_id': 'camp-uuid-456',
                'lead_id': 'lead-uuid-789',
                'auto_reply_sent': False,
                'user_replied': False,
                'auto_reply_enabled': True,
                'auto_reply_message_text': 'Question pitch text',
                'auto_reply_media_path': None,
                'contact_username': 'test_lead',
                'channel_username': 'test_chan'
            }
            self.mock_cursor.fetchone.return_value = matched_row

            # Simulate: During sleep, fallback marks autoreply_dispatched:log-uuid-123
            original_sleep = asyncio.sleep
            async def patched_sleep(seconds):
                # When delay starts, simulate fallback dispatching
                self.redis_store['autoreply_dispatched:log-uuid-123'] = "1"
                return

            with patch('asyncio.sleep', side_effect=patched_sleep), \
                 patch('app.outreach.auto_reply.is_kill_switch_active', return_value=(False, None)), \
                 patch('app.outreach.auto_reply.is_outreach_enabled', return_value=True), \
                 patch('app.outreach.auto_reply.is_dry_run', return_value=False):
                await handler(mock_event)

            # Crucial assertion: send_message was NEVER called because post-sleep check caught it!
            self.mock_client.send_message.assert_not_called()
            self.mock_client.send_file.assert_not_called()

        asyncio.run(run_test())

    def test_post_sleep_dedup_aborts_if_db_updated_during_delay(self):
        """If DB auto_reply_sent becomes True during delay, real-time handler must abort."""
        async def run_test():
            self.engine.register_handler()
            handler = self.engine._registered_handler

            mock_event = MagicMock()
            mock_event.is_private = True
            mock_event.out = False
            mock_event.sender_id = 777777
            mock_event.chat_id = 777777
            mock_sender = MagicMock()
            mock_sender.bot = False
            mock_sender.username = "db_lead"
            mock_event.get_sender = AsyncMock(return_value=mock_sender)

            matched_row = {
                'log_id': 'log-uuid-db',
                'campaign_id': 'camp-1',
                'lead_id': 'lead-1',
                'auto_reply_sent': False,
                'user_replied': False,
                'auto_reply_enabled': True,
                'auto_reply_message_text': 'Pitch question',
                'auto_reply_media_path': None,
                'contact_username': 'db_lead',
                'channel_username': 'chan_db'
            }

            # First query returns unreplied lead, second query (re-verification) returns auto_reply_sent=True
            self.mock_cursor.fetchone.side_effect = [
                matched_row,
                {'auto_reply_sent': True}
            ]

            with patch('asyncio.sleep', AsyncMock()), \
                 patch('app.outreach.auto_reply.is_kill_switch_active', return_value=(False, None)), \
                 patch('app.outreach.auto_reply.is_outreach_enabled', return_value=True), \
                 patch('app.outreach.auto_reply.is_dry_run', return_value=False):
                await handler(mock_event)

            self.mock_client.send_message.assert_not_called()

        asyncio.run(run_test())

    def test_fallback_skips_in_flight_leads(self):
        """Fallback loop must skip leads currently marked as in-flight by real-time handler."""
        async def run_test():
            # Mark log in flight in Redis
            self.redis_store['autoreply_in_flight:log-inflight-999'] = "1"

            camp_row = {
                'id': 'camp-1',
                'auto_reply_enabled': True,
                'auto_reply_message_text': 'Fallback pitch',
                'auto_reply_media_path': None
            }
            unreplied_rows = [{
                'log_id': 'log-inflight-999',
                'contact_username': 'inflight_user',
                'telegram_user_id': 999
            }]

            self.mock_cursor.fetchone.return_value = camp_row
            self.mock_cursor.fetchall.return_value = unreplied_rows

            # Let fallback_loop run one iteration then stop
            async def stop_after_one_loop(*args, **kwargs):
                self.shutdown_event.set()

            with patch('asyncio.sleep', side_effect=stop_after_one_loop), \
                 patch('app.outreach.auto_reply.is_kill_switch_active', return_value=(False, None)), \
                 patch('app.outreach.auto_reply.is_outreach_enabled', return_value=True), \
                 patch('app.outreach.auto_reply.is_dry_run', return_value=False):
                await self.engine.fallback_loop()

            self.mock_client.send_message.assert_not_called()

        asyncio.run(run_test())

    def test_successful_single_send_updates_db_and_keys(self):
        """When a message is successfully sent, DB and Redis completion keys must be updated."""
        async def run_test():
            self.engine.register_handler()
            handler = self.engine._registered_handler

            mock_event = MagicMock()
            mock_event.is_private = True
            mock_event.out = False
            mock_event.sender_id = 888888
            mock_event.chat_id = 888888
            mock_sender = MagicMock()
            mock_sender.bot = False
            mock_sender.username = "success_user"
            mock_event.get_sender = AsyncMock(return_value=mock_sender)

            matched_row = {
                'log_id': 'log-uuid-success',
                'campaign_id': 'camp-1',
                'lead_id': 'lead-1',
                'auto_reply_sent': False,
                'user_replied': False,
                'auto_reply_enabled': True,
                'auto_reply_message_text': 'Hello pitch',
                'auto_reply_media_path': None,
                'contact_username': 'success_user',
                'channel_username': 'chan_ok'
            }

            self.mock_cursor.fetchone.side_effect = [
                matched_row,
                {'auto_reply_sent': False}
            ]

            with patch('asyncio.sleep', AsyncMock()), \
                 patch('app.outreach.auto_reply.is_kill_switch_active', return_value=(False, None)), \
                 patch('app.outreach.auto_reply.is_outreach_enabled', return_value=True), \
                 patch('app.outreach.auto_reply.is_dry_run', return_value=False):
                await handler(mock_event)

            self.mock_client.send_message.assert_called_once_with(888888, 'Hello pitch')
            self.assertEqual(self.redis_store.get('autoreply_done:log-uuid-success'), "1")
            self.assertEqual(self.redis_store.get('autoreply_done:888888'), "1")
            self.assertEqual(self.redis_store.get('autoreply_done:success_user'), "1")
            self.assertIsNone(self.redis_store.get('autoreply_in_flight:log-uuid-success'))

        asyncio.run(run_test())


if __name__ == '__main__':
    unittest.main()
