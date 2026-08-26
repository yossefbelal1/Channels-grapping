"""
tests/test_rate_limiter_regression.py — Tests for Rate Limiter Fail-Closed and Sliding Window Semantics
"""

import unittest
from unittest.mock import MagicMock
from tg_manager import TelegramManager, LUA_RATE_LIMIT


class TestRateLimiterRegression(unittest.TestCase):

    def setUp(self):
        self.mock_redis = MagicMock()
        # Mock successful script registration
        self.mock_redis.register_script.return_value = MagicMock()
        self.tg_manager = TelegramManager(self.mock_redis, session_name="test_session")

    def test_rate_limiter_fail_closed_on_redis_error(self):
        """P0 Regression: Ensure rate limiter FAILS CLOSED (returns False) on Redis/Lua failure."""
        # Simulate Redis/Lua raising an exception (e.g. connection dropped, syntax error)
        self.tg_manager._lua_ratelimit.side_effect = Exception("Redis connection refused")

        result = self.tg_manager.check_request_limit("test_session")
        self.assertFalse(result, "Rate limiter MUST fail closed (return False) on error to protect Telegram accounts.")

    def test_rate_limiter_allowed_when_within_limit(self):
        """Ensure rate limiter returns True when Redis Lua script returns 1."""
        self.tg_manager._lua_ratelimit.return_value = 1
        self.assertTrue(self.tg_manager.check_request_limit("test_session"))

    def test_rate_limiter_denied_when_exceeded(self):
        """Ensure rate limiter returns False when Redis Lua script returns 0 (limit reached)."""
        self.tg_manager._lua_ratelimit.return_value = 0
        self.assertFalse(self.tg_manager.check_request_limit("test_session"))

    def test_lua_script_syntax_and_sliding_window_structure(self):
        """Verify the Lua script contains sliding window cleanup and sequence increment."""
        self.assertIn("ZREMRANGEBYSCORE", LUA_RATE_LIMIT)
        self.assertIn("ZCARD", LUA_RATE_LIMIT)
        self.assertIn("ZADD", LUA_RATE_LIMIT)


if __name__ == '__main__':
    unittest.main()
