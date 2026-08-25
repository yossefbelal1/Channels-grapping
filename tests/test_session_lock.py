"""
tests/test_session_lock.py — Tests for Distributed Session Locking & Compare-and-Delete
"""

import unittest
from unittest.mock import MagicMock
from tg_manager import LUA_RELEASE_LOCK, LUA_RENEW_LOCK


class TestDistributedLockLogic(unittest.TestCase):

    def test_owner_identity_format(self):
        import socket
        import os
        import uuid
        owner_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        parts = owner_id.split(':')
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[1], str(os.getpid()))

    def test_release_lock_lua_semantics(self):
        # Verify Lua script structure for atomic compare-and-delete
        self.assertIn('redis.call("get", KEYS[1]) == ARGV[1]', LUA_RELEASE_LOCK)
        self.assertIn('redis.call("del", KEYS[1])', LUA_RELEASE_LOCK)

    def test_renew_lock_lua_semantics(self):
        # Verify Lua script structure for atomic compare-and-expire
        self.assertIn('redis.call("get", KEYS[1]) == ARGV[1]', LUA_RENEW_LOCK)
        self.assertIn('redis.call("expire", KEYS[1], ARGV[2])', LUA_RENEW_LOCK)


if __name__ == '__main__':
    unittest.main()
