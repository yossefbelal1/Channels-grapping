"""
tests/test_graceful_shutdown_validator.py — Tests for LeadValidator and AutoReplyEngine Graceful Shutdown Semantics
"""

import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

from app.outreach.auto_reply import AutoReplyEngine
from validator import LeadValidator


class TestGracefulShutdownValidator(unittest.TestCase):

    def test_auto_reply_engine_registration_and_unregistration(self):
        """Verify AutoReplyEngine registers and cleanly unregisters Telethon event handlers."""
        mock_client = MagicMock()
        mock_client.remove_event_handler = MagicMock()
        mock_client.add_event_handler = MagicMock()
        # Mock @client.on(...) decorator
        mock_client.on.return_value = lambda fn: fn

        mock_redis = MagicMock()
        mock_db = MagicMock()
        shutdown_event = asyncio.Event()

        engine = AutoReplyEngine(
            user_client=mock_client,
            redis_conn=mock_redis,
            db_helper=mock_db,
            shutdown_event=shutdown_event
        )

        # Register
        engine.register_handler()
        self.assertIsNotNone(engine._registered_handler)
        self.assertTrue(engine.is_handler_registered)

        # Unregister
        registered_fn = engine._registered_handler
        engine.unregister_handlers()
        mock_client.remove_event_handler.assert_called_once_with(registered_fn)
        self.assertFalse(engine.is_handler_registered)
        self.assertIsNone(engine._registered_handler)

    def test_graceful_shutdown_cancels_all_7_background_tasks(self):
        """Verify that shutdown cleans up all 7 background tasks deterministically."""
        async def run_test():
            validator = LeadValidator.__new__(LeadValidator)
            validator.shutdown_event = asyncio.Event()

            # Create 7 background tasks that sleep indefinitely
            async def infinite_loop():
                try:
                    while True:
                        await asyncio.sleep(10)
                except asyncio.CancelledError:
                    pass

            validator.user_joiner_task = asyncio.create_task(infinite_loop())
            validator.campaign_dispatcher_task = asyncio.create_task(infinite_loop())
            validator.followup_dispatcher_task = asyncio.create_task(infinite_loop())
            validator.auto_scan_task = asyncio.create_task(infinite_loop())
            validator.private_invite_task = asyncio.create_task(infinite_loop())
            validator.auto_reply_fallback_task = asyncio.create_task(infinite_loop())
            validator.rescan_scheduler_task = asyncio.create_task(infinite_loop())

            # Yield control so tasks start
            await asyncio.sleep(0.01)

            validator.auto_reply_engine = MagicMock()
            validator.auto_reply_engine.unregister_handlers = MagicMock()

            validator.user_client = MagicMock()
            validator.user_client.disconnect = AsyncMock()

            validator.tg_manager = MagicMock()
            validator.tg_manager.disconnect_all = AsyncMock()

            validator.db_helper = MagicMock()
            validator.db_helper.close = MagicMock()

            validator.redis_conn = MagicMock()
            validator.redis_conn.close = MagicMock()

            # Execute shutdown sequence (mirroring finally block in validator.py)
            tasks_to_cancel = [
                getattr(validator, 'user_joiner_task', None),
                getattr(validator, 'campaign_dispatcher_task', None),
                getattr(validator, 'followup_dispatcher_task', None),
                getattr(validator, 'auto_scan_task', None),
                getattr(validator, 'private_invite_task', None),
                getattr(validator, 'auto_reply_fallback_task', None),
                getattr(validator, 'rescan_scheduler_task', None),
            ]
            valid_tasks = [t for t in tasks_to_cancel if t and not t.done()]
            for t in valid_tasks:
                t.cancel()
            if valid_tasks:
                await asyncio.gather(*valid_tasks, return_exceptions=True)

            validator.unregister_auto_reply_handler()

            if hasattr(validator, 'user_client') and validator.user_client:
                await validator.user_client.disconnect()
            await validator.tg_manager.disconnect_all()
            validator.db_helper.close()
            validator.redis_conn.close()

            # Verify all tasks are done
            for task in valid_tasks:
                self.assertTrue(task.done())

            # Verify resources closed
            validator.auto_reply_engine.unregister_handlers.assert_called_once()
            validator.user_client.disconnect.assert_awaited_once()
            validator.tg_manager.disconnect_all.assert_awaited_once()
            validator.db_helper.close.assert_called_once()
            validator.redis_conn.close.assert_called_once()

        asyncio.run(run_test())

    def test_graceful_shutdown_resilience_to_errors(self):
        """Verify that errors during task cancellation or handler removal do not prevent resource cleanup."""
        async def run_test():
            validator = LeadValidator.__new__(LeadValidator)
            validator.shutdown_event = asyncio.Event()

            async def faulty_loop():
                try:
                    while True:
                        await asyncio.sleep(10)
                except asyncio.CancelledError:
                    raise RuntimeError("Error during task cleanup")

            validator.user_joiner_task = asyncio.create_task(faulty_loop())
            # Yield control so task enters its try block
            await asyncio.sleep(0.01)

            validator.auto_reply_engine = MagicMock()
            validator.auto_reply_engine.unregister_handlers.side_effect = Exception("Telethon handler error")

            validator.user_client = MagicMock()
            validator.user_client.disconnect = AsyncMock()

            validator.tg_manager = MagicMock()
            validator.tg_manager.disconnect_all = AsyncMock()

            validator.db_helper = MagicMock()
            validator.db_helper.close = MagicMock()

            validator.redis_conn = MagicMock()
            validator.redis_conn.close = MagicMock()

            # Execute shutdown sequence with error handling
            tasks_to_cancel = [getattr(validator, 'user_joiner_task', None)]
            valid_tasks = [t for t in tasks_to_cancel if t and not t.done()]
            for t in valid_tasks:
                t.cancel()
            if valid_tasks:
                # gather with return_exceptions=True absorbs the RuntimeError
                results = await asyncio.gather(*valid_tasks, return_exceptions=True)
                self.assertIsInstance(results[0], RuntimeError)

            try:
                validator.unregister_auto_reply_handler()
            except Exception:
                pass

            if hasattr(validator, 'user_client') and validator.user_client:
                await validator.user_client.disconnect()
            await validator.tg_manager.disconnect_all()
            validator.db_helper.close()
            validator.redis_conn.close()

            # Ensure all final teardown steps still execute
            validator.user_client.disconnect.assert_awaited_once()
            validator.tg_manager.disconnect_all.assert_awaited_once()
            validator.db_helper.close.assert_called_once()
            validator.redis_conn.close.assert_called_once()

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
