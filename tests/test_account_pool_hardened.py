"""
tests/test_account_pool_hardened.py — Test Suite for Account Pool States & Centralized Retry
"""

import pytest
from unittest.mock import MagicMock

from app.core.telegram_pool import (
    AccountState,
    AccountPoolManager,
    RetryPolicy,
    MembershipManager
)


def test_account_states_completeness():
    assert AccountState.HEALTHY == "HEALTHY"
    assert AccountState.BUSY == "BUSY"
    assert AccountState.COOLDOWN == "COOLDOWN"
    assert AccountState.FLOOD_WAIT == "FLOOD_WAIT"
    assert AccountState.UNAVAILABLE == "UNAVAILABLE"
    assert AccountState.RECOVERING == "RECOVERING"
    assert set(AccountState.ACTIVE) == {"HEALTHY", "RECOVERING"}


def test_retry_policy_exponential_backoff_and_jitter():
    policy = RetryPolicy(base_backoff=2.0, max_backoff=30.0, jitter_factor=0.2)

    # Attempt 0: base 2.0 * 1 = 2.0, with jitter +/- 20% -> [1.6, 2.4]
    b0 = policy.compute_backoff(0)
    assert 1.5 <= b0 <= 2.5

    # Attempt 2: base 2.0 * 4 = 8.0, with jitter +/- 20% -> [6.4, 9.6]
    b2 = policy.compute_backoff(2)
    assert 6.0 <= b2 <= 10.0

    # High attempt capped at max_backoff = 30.0 (+/- 20%)
    b10 = policy.compute_backoff(10)
    assert 23.0 <= b10 <= 37.0


def test_retry_policy_permanent_error_detection():
    policy = RetryPolicy()

    # Permanent errors
    class UsernameNotOccupiedError(Exception):
        pass
    class ChannelPrivateError(Exception):
        pass
    class AuthKeyInvalidError(Exception):
        pass

    assert policy.is_permanent_error(UsernameNotOccupiedError("Username not occupied")) is True
    assert policy.is_permanent_error(ChannelPrivateError("Private channel")) is True
    assert policy.is_permanent_error(AuthKeyInvalidError("Key invalid")) is True
    assert policy.is_permanent_error(ValueError("Entity not found")) is True

    # Transient errors
    class FloodWaitError(Exception):
        pass
    class TimedOutError(Exception):
        pass

    assert policy.is_permanent_error(FloodWaitError("Wait 10 seconds")) is False
    assert policy.is_permanent_error(TimedOutError("Connection timed out")) is False


def test_account_pool_select_least_loaded():
    mock_redis = MagicMock()
    mgr = AccountPoolManager(redis_conn=mock_redis)

    # Mock telemetry
    def fake_get(key):
        if "acc_1" in key:
            return "HEALTHY"
        elif "acc_2" in key:
            return "HEALTHY"
        elif "acc_3" in key:
            return "FLOOD_WAIT"
        return "HEALTHY"

    mock_redis.get.side_effect = fake_get

    def fake_hgetall(key):
        if "acc_1" in key:
            return {b"active_jobs": b"5", b"recent_error_count": b"2"}
        elif "acc_2" in key:
            return {b"active_jobs": b"0", b"recent_error_count": b"0"}
        return {}

    mock_redis.hgetall.side_effect = fake_hgetall

    selected = mgr.select_least_loaded(["acc_1", "acc_2", "acc_3"])
    # acc_3 is in FLOOD_WAIT, acc_1 has 5 active jobs, acc_2 has 0 active jobs -> acc_2 selected
    assert selected == "acc_2"
