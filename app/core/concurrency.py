"""
app/core/concurrency.py — Centralized Concurrency & Task Bounding Governance

Provides bounded execution primitives using asyncio.Semaphore to prevent
FloodWait spikes, API bursts, and resource exhaustion across discovery workers.
"""

import os
import asyncio
import logging
from typing import Any, Callable, Coroutine, Iterable, List, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Configurable bounds via environment variables
DEFAULT_MAX_CONCURRENT_TASKS = int(os.getenv("MAX_CONCURRENT_TASKS", "50"))
DEFAULT_MAX_SESSION_CONCURRENCY = int(os.getenv("MAX_SESSION_CONCURRENCY", "5"))


class GlobalConcurrencyLimiter:
    """
    Process-wide semaphore limiter to cap the number of active concurrent tasks.
    """
    _instance: Optional["GlobalConcurrencyLimiter"] = None
    _semaphore: Optional[asyncio.Semaphore] = None

    def __init__(self, max_concurrent: int = DEFAULT_MAX_CONCURRENT_TASKS):
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    @classmethod
    def get_instance(cls, max_concurrent: Optional[int] = None) -> "GlobalConcurrencyLimiter":
        if cls._instance is None:
            limit = max_concurrent or DEFAULT_MAX_CONCURRENT_TASKS
            cls._instance = cls(limit)
        return cls._instance

    @property
    def semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_concurrent)
        return self._semaphore

    async def run(self, coro: Coroutine[Any, Any, T]) -> T:
        """Executes a coroutine within the global concurrency semaphore."""
        async with self.semaphore:
            return await coro


class SessionConcurrencyLimiter:
    """
    Per-session semaphore limiter to cap concurrent requests to any single Telethon session.
    Prevents parallel request collisions on SQLite session files and per-account FloodWait.
    """
    _limiters: dict = {}

    @classmethod
    def get_limiter(cls, session_name: str, max_concurrent: int = DEFAULT_MAX_SESSION_CONCURRENCY) -> asyncio.Semaphore:
        if session_name not in cls._limiters:
            cls._limiters[session_name] = asyncio.Semaphore(max_concurrent)
        return cls._limiters[session_name]


async def bounded_gather(
    *coros_or_futures: Coroutine[Any, Any, T],
    semaphore: Optional[asyncio.Semaphore] = None,
    limit: Optional[int] = None,
    max_concurrent: Optional[int] = None,
    return_exceptions: bool = True
) -> List[Any]:
    """
    Runs an iterable of coroutines concurrently, bounded by an asyncio.Semaphore.
    Replaces unbounded asyncio.gather to prevent overwhelming external APIs and memory.
    """
    if not coros_or_futures:
        return []

    concurrency_limit = limit or max_concurrent
    sem = semaphore or (asyncio.Semaphore(concurrency_limit) if concurrency_limit else GlobalConcurrencyLimiter.get_instance().semaphore)

    async def _worker(coro):
        async with sem:
            return await coro

    wrapped_tasks = [_worker(c) for c in coros_or_futures]
    return await asyncio.gather(*wrapped_tasks, return_exceptions=return_exceptions)
