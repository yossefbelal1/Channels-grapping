"""
tests/test_rate_limiter_failure_injection.py — Failure injection tests for TelegramManager rate limiter
"""

import unittest
from unittest.mock import MagicMock, patch
from tg_manager import TelegramManager, LUA_RATE_LIMIT


class TestRateLimiterFailureInjection(unittest.TestCase):

    def setUp(self):
        self.mock_redis = MagicMock()
        self.mock_redis.register_script.return_value = MagicMock()
        self.tg_manager = TelegramManager(self.mock_redis, session_name="test_session")

    def test_case_1_redis_connection_refused_fails_closed(self):
        """P0-D Failure Injection: Redis connection dropped -> Rate limiter must return False (deny request)."""
        self.tg_manager._lua_ratelimit.side_effect = Exception("Connection refused: 127.0.0.1:6379")
        result = self.tg_manager.check_request_limit("test_session")
        self.assertFalse(result, "Rate limiter MUST fail closed (return False) when Redis connection is down.")

    def test_case_2_lua_execution_runtime_error_fails_closed(self):
        """P0-D Failure Injection: Lua syntax or Redis runtime error -> Rate limiter must return False."""
        self.tg_manager._lua_ratelimit.side_effect = Exception("ERR Error running script (call to f_...): @user_script:1: error")
        result = self.tg_manager.check_request_limit("test_session")
        self.assertFalse(result, "Rate limiter MUST fail closed (return False) on Lua script error.")

    def test_case_3_redis_socket_timeout_fails_closed(self):
        """P0-D Failure Injection: Redis socket timeout -> Rate limiter must return False."""
        self.tg_manager._lua_ratelimit.side_effect = TimeoutError("Redis socket read timed out")
        result = self.tg_manager.check_request_limit("test_session")
        self.assertFalse(result, "Rate limiter MUST fail closed (return False) on socket timeout.")

    def test_case_4_malformed_lua_response_fails_closed(self):
        """P0-D Failure Injection: Unexpected return value (None / string) -> Rate limiter must return False."""
        self.tg_manager._lua_ratelimit.return_value = None
        result = self.tg_manager.check_request_limit("test_session")
        self.assertFalse(result, "Rate limiter MUST return False if return value is not 1.")

    def test_case_5_normal_operation_under_limit_allowed(self):
        """P0-D: Under rate limit, request is permitted."""
        self.tg_manager._lua_ratelimit.return_value = 1
        result = self.tg_manager.check_request_limit("test_session")
        self.assertTrue(result)

    def test_case_6_rate_limit_exceeded_denied(self):
        """P0-D: When rate limit is exceeded, request is denied (0 returned from Lua)."""
        self.tg_manager._lua_ratelimit.return_value = 0
        result = self.tg_manager.check_request_limit("test_session")
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
