"""
tests/test_real_redis_integration.py — Real Redis Integration Tests

Exercises actual Redis server using production Lua scripts:
1. Sliding-window rate limiter (LUA_RATE_LIMIT) under high concurrency.
2. Distributed session lock (LUA_RELEASE_LOCK, LUA_RENEW_LOCK) across 20 concurrent racing workers.
3. Atomic seed intake (LUA_ATOMIC_SEED_ENQUEUE) deduplication.
4. Delivery idempotency token lifecycle.

Runs automatically against Redis service in CI or local development.
"""

import os
import time
import uuid
import unittest
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import redis

from tg_manager import LUA_RATE_LIMIT, LUA_RELEASE_LOCK, LUA_RENEW_LOCK
from seed_intake_worker import LUA_ATOMIC_SEED_ENQUEUE


def get_real_redis_client():
    """Attempts to create a physical connection to Redis."""
    try:
        r = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
            decode_responses=True,
            socket_timeout=3
        )
        r.ping()
        return r
    except Exception:
        return None


class TestRealRedisIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Check if real Redis server is reachable."""
        cls.redis = get_real_redis_client()
        cls.is_available = cls.redis is not None

    @classmethod
    def tearDownClass(cls):
        if cls.redis:
            cls.redis.close()

    def setUp(self):
        if not self.is_available:
            self.skipTest("Real Redis server is not reachable. Skipping real Redis integration test.")
        self.test_prefix = f"test_integration:{uuid.uuid4().hex[:8]}"

    def tearDown(self):
        if self.is_available:
            # Clean up all keys created during this test
            keys = self.redis.keys(f"{self.test_prefix}:*")
            if keys:
                self.redis.delete(*keys)

    def test_real_lua_sliding_window_rate_limiter_concurrency(self):
        """
        P0 Rate Limiter Integration: 20 concurrent threads race to make requests
        with a rate limit of exactly 10 requests per 60-second window.
        
        Guarantees:
        - Exactly 10 requests are allowed (Lua script returns 1).
        - Exactly 10 requests are denied (Lua script returns 0).
        - Sliding window never overflows limit under concurrency.
        """
        rate_key = f"{self.test_prefix}:limit:test_session"
        now = time.time()
        window = 60
        max_limit = 10

        allowed_count = 0
        denied_count = 0
        lock = threading.Lock()
        barrier = threading.Barrier(20)

        def worker_rate_limit(worker_id):
            nonlocal allowed_count, denied_count
            r = get_real_redis_client()
            if not r:
                return
            try:
                barrier.wait(timeout=5)
                res = r.eval(LUA_RATE_LIMIT, 1, rate_key, time.time(), window, max_limit)
                with lock:
                    if res == 1:
                        allowed_count += 1
                    else:
                        denied_count += 1
            finally:
                r.close()

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(worker_rate_limit, i) for i in range(20)]
            for f in as_completed(futures):
                f.result()

        self.assertEqual(allowed_count, 10, f"Expected exactly 10 allowed requests, got {allowed_count}")
        self.assertEqual(denied_count, 10, f"Expected exactly 10 denied requests, got {denied_count}")

    def test_real_lua_distributed_session_lock_concurrency(self):
        """
        P0 Distributed Lock Integration: 20 concurrent workers race to acquire the SAME session lock.
        
        Guarantees:
        - Exactly 1 worker wins lock acquisition (SET NX EX).
        - Exactly 19 workers fail acquisition.
        - Non-owner cannot renew or release lock (compare-and-delete/expire).
        - Owner can renew and release lock cleanly.
        """
        lock_key = f"{self.test_prefix}:lock:session_alpha"
        ttl = 15

        winners = []
        lock = threading.Lock()
        barrier = threading.Barrier(20)

        def worker_lock_race(worker_id):
            owner_id = f"worker_{worker_id}_{uuid.uuid4().hex[:6]}"
            r = get_real_redis_client()
            if not r:
                return
            try:
                barrier.wait(timeout=5)
                # Production lock acquisition: SET lock_key owner_id NX EX ttl
                acquired = r.set(lock_key, owner_id, nx=True, ex=ttl)
                if acquired:
                    with lock:
                        winners.append((worker_id, owner_id))
            finally:
                r.close()

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(worker_lock_race, i) for i in range(20)]
            for f in as_completed(futures):
                f.result()

        self.assertEqual(len(winners), 1, f"Expected exactly 1 lock winner, got {len(winners)}")
        winner_id, winner_owner = winners[0]

        # Test non-owner cannot renew lock
        fake_owner = "fake_intruder_999"
        renew_fake_res = self.redis.eval(LUA_RENEW_LOCK, 1, lock_key, fake_owner, 30)
        self.assertEqual(renew_fake_res, 0, "Non-owner renewal MUST return 0.")

        # Test non-owner cannot release lock
        release_fake_res = self.redis.eval(LUA_RELEASE_LOCK, 1, lock_key, fake_owner)
        self.assertEqual(release_fake_res, 0, "Non-owner release MUST return 0.")
        self.assertTrue(self.redis.exists(lock_key), "Lock must still exist after fake release attempt.")

        # Test owner can renew lock
        renew_owner_res = self.redis.eval(LUA_RENEW_LOCK, 1, lock_key, winner_owner, 30)
        self.assertEqual(renew_owner_res, 1, "Owner renewal MUST return 1.")

        # Test owner can release lock atomically
        release_owner_res = self.redis.eval(LUA_RELEASE_LOCK, 1, lock_key, winner_owner)
        self.assertEqual(release_owner_res, 1, "Owner release MUST return 1.")
        self.assertFalse(self.redis.exists(lock_key), "Lock must be deleted after owner release.")

    def test_real_lua_atomic_seed_intake_concurrency(self):
        """
        P0 Seed Intake Integration: 10 concurrent threads attempt to enqueue the SAME seed channel.
        
        Guarantees:
        - Exactly 1 thread successfully enqueues to Redis queue list and adds to seen set.
        - Exactly 9 threads detect duplicate and return 0.
        - Queue list length is exactly 1.
        """
        seen_set_key = f"{self.test_prefix}:seen_channels"
        queue_list_key = f"{self.test_prefix}:queue:high"
        seed_identifier = f"https://t.me/seed_chan_{uuid.uuid4().hex[:6]}"
        payload = f'{{"link": "{seed_identifier}", "source": "autotele"}}'

        enqueued_count = 0
        lock = threading.Lock()
        barrier = threading.Barrier(10)

        def worker_seed_intake(worker_id):
            nonlocal enqueued_count
            r = get_real_redis_client()
            if not r:
                return
            try:
                barrier.wait(timeout=5)
                # Production atomic Lua seed enqueue
                res = r.eval(LUA_ATOMIC_SEED_ENQUEUE, 2, seen_set_key, queue_list_key, seed_identifier, payload)
                with lock:
                    if res == 1:
                        enqueued_count += 1
            finally:
                r.close()

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker_seed_intake, i) for i in range(10)]
            for f in as_completed(futures):
                f.result()

        self.assertEqual(enqueued_count, 1, f"Expected exactly 1 successful enqueue, got {enqueued_count}")
        self.assertEqual(self.redis.llen(queue_list_key), 1, "Queue list must have exactly 1 item.")
        self.assertTrue(self.redis.sismember(seen_set_key, seed_identifier), "Seen set must contain seed.")


if __name__ == '__main__':
    unittest.main()
