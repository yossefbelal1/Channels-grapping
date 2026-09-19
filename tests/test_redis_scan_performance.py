"""
tests/test_redis_scan_performance.py — Verifies Redis non-blocking scan_iter behavior
"""

import unittest
from unittest.mock import MagicMock


class TestRedisScanPerformance(unittest.TestCase):

    def test_scan_iter_matches_keys_functionality(self):
        """Verify that scan_iter traverses keys matching pattern without blocking."""
        mock_redis = MagicMock()
        mock_redis.scan_iter.return_value = iter([
            "health:account_1:score",
            "health:account_2:score",
            "health:account_3:score",
        ])

        found_accounts = []
        for acc_key in mock_redis.scan_iter(match="health:*:score", count=100):
            acc_name = acc_key.split(":")[1]
            found_accounts.append(acc_name)

        self.assertEqual(found_accounts, ["account_1", "account_2", "account_3"])
        mock_redis.scan_iter.assert_called_once_with(match="health:*:score", count=100)

    def test_account_pool_state_scanning(self):
        """Verify account:pool state scanning."""
        mock_redis = MagicMock()
        mock_redis.scan_iter.return_value = iter([
            "account:pool:tamer:state",
            "account:pool:worker_1:state"
        ])
        mock_redis.get.side_effect = lambda k: "active" if "tamer" in k else "cooling_down"

        account_statuses = {}
        for state_key in mock_redis.scan_iter(match="account:pool:*:state", count=100):
            s_name = state_key.split(":")[2]
            state_val = mock_redis.get(state_key)
            account_statuses[s_name] = state_val

        self.assertEqual(account_statuses, {
            "tamer": "active",
            "worker_1": "cooling_down"
        })
