"""
tests/test_concurrency_governance.py — Unit tests for Centralized Concurrency & Bounded Governance
"""

import asyncio
import pytest
from app.core.concurrency import (
    GlobalConcurrencyLimiter,
    SessionConcurrencyLimiter,
    bounded_gather
)


@pytest.mark.asyncio
async def test_bounded_gather_limits_concurrency():
    active_count = 0
    max_observed = 0

    async def sample_task(val: int):
        nonlocal active_count, max_observed
        active_count += 1
        max_observed = max(max_observed, active_count)
        await asyncio.sleep(0.05)
        active_count -= 1
        return val * 2

    tasks = [sample_task(i) for i in range(10)]
    results = await bounded_gather(*tasks, limit=3)

    assert len(results) == 10
    assert results == [i * 2 for i in range(10)]
    assert max_observed <= 3, f"Max concurrent tasks observed was {max_observed}, expected <= 3"


@pytest.mark.asyncio
async def test_session_concurrency_limiter_distinct_semaphores():
    sem1 = SessionConcurrencyLimiter.get_limiter("acc_1", max_concurrent=2)
    sem2 = SessionConcurrencyLimiter.get_limiter("acc_2", max_concurrent=3)
    sem1_again = SessionConcurrencyLimiter.get_limiter("acc_1")

    assert sem1 is sem1_again
    assert sem1 is not sem2
