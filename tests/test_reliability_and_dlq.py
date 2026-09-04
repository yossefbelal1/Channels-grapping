"""
tests/test_reliability_and_dlq.py — Test Suite for Job Idempotency, DLQ, and Envelope Semantics
"""

import pytest
from unittest.mock import MagicMock

from app.core.reliability import (
    JobEnvelope,
    IdempotencyGuard,
    DeadLetterQueueManager
)


def test_job_envelope_wrap_and_unwrap():
    payload = {
        "channel_username": "dubai_gold_signals",
        "link": "https://t.me/dubai_gold_signals",
        "attempt_count": 1
    }
    envelope = JobEnvelope.wrap(payload, max_attempts=5)
    assert envelope["job_id"] is not None
    assert envelope["idempotency_key"] == "job:https://t.me/dubai_gold_signals"
    assert envelope["max_attempts"] == 5

    unwrapped_payload, meta = JobEnvelope.unwrap(envelope)
    assert unwrapped_payload["channel_username"] == "dubai_gold_signals"
    assert meta["job_id"] == envelope["job_id"]
    assert meta["attempt_count"] == 1


def test_idempotency_guard_acquire_and_release():
    mock_redis = MagicMock()
    mock_redis.set.return_value = True

    guard = IdempotencyGuard(redis_conn=mock_redis, ttl_seconds=3600)
    assert guard.acquire("channel_test_key") is True
    assert mock_redis.set.called

    guard.release("channel_test_key")
    mock_redis.delete.assert_called_with("idempotency:lock:channel_test_key")


def test_dead_letter_queue_push():
    mock_redis = MagicMock()
    mock_redis.llen.return_value = 1

    dlq = DeadLetterQueueManager(redis_conn=mock_redis, dlq_name="queue:dead_letter")
    job = {"job_id": "test_job_1", "payload": {"username": "bad_channel"}}

    success = dlq.send_to_dlq(
        job_envelope=job,
        error_type="ChannelPrivateError",
        error_message="Channel is private and inaccessible",
        origin_queue="queue:normal"
    )
    assert success is True
    assert mock_redis.lpush.called
    assert dlq.get_dlq_depth() == 1
