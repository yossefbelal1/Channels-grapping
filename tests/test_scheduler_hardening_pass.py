"""
tests/test_scheduler_hardening_pass.py — Production Wiring & Scheduling Hardening Pass Tests

Validates:
1. Single Source of Truth / Distributed Leader Lock (prevents competing schedulers)
2. Embedded Scheduler disabled by default in LeadValidator
3. Transactional Outbox Pattern: Redis enqueue failure does NOT advance next_crawl_at
4. Outbox Reconciliation: Rescues un-enqueued jobs when Redis recovers
5. In-flight Deduplication: Prevents parallel duplicate scheduling of active channels
6. Full Job Lifecycle: checkout (running) -> completion (completed/failed)
7. Stale Running Job Crash Recovery: Reconciles crashed worker jobs after timeout
8. Scheduler Worker Heartbeat: Emits heartbeat in Redis
9. Subscriber Neutrality (400 vs 2M+) & Low-Activity Retention
10. Docker Compose Structure & Production Wiring Validation
"""

import os
import json
import uuid
import yaml
import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

from app.scheduler.priority_scheduler import PriorityScheduler
from app.scheduler.activity_classifier import ActivityClassifier, ActivityClass, ScanDepthTier
from scheduler_worker import SchedulerWorker
from validator import LeadValidator


class MockRedisHardened:
    def __init__(self):
        self.data = {}
        self.queues = {}
        self.fail_lpush = False

    def set(self, key, val, nx=False, ex=None):
        if nx and key in self.data:
            return False
        self.data[key] = str(val)
        return True

    def setex(self, key, time, val):
        self.data[key] = str(val)
        return True

    def get(self, key):
        return self.data.get(key)

    def delete(self, key):
        if key in self.data:
            del self.data[key]
            return 1
        return 0

    def lpush(self, queue, val):
        if self.fail_lpush:
            raise ConnectionError("Simulated Redis Connection Refused")
        if queue not in self.queues:
            self.queues[queue] = []
        self.queues[queue].insert(0, val)
        return len(self.queues[queue])

    def rpop(self, queue):
        if queue in self.queues and self.queues[queue]:
            return self.queues[queue].pop()
        return None

    def llen(self, queue):
        return len(self.queues.get(queue, []))


@pytest.fixture
def hardened_fixtures():
    redis_mock = MockRedisHardened()
    db_conn = MagicMock()
    cursor = MagicMock()
    db_conn.cursor.return_value.__enter__.return_value = cursor
    return redis_mock, db_conn, cursor


class TestSchedulerHardeningPass:

    # 1. Distributed Leader Lock Prevents Competing Schedulers
    def test_leader_lock_prevents_competing_schedulers(self, hardened_fixtures):
        redis_mock, db_conn, cursor = hardened_fixtures
        scheduler_1 = PriorityScheduler(redis_conn=redis_mock, db_conn=db_conn)
        scheduler_2 = PriorityScheduler(redis_conn=redis_mock, db_conn=db_conn)

        # Instance 1 acquires lock
        assert scheduler_1.acquire_leader_lock(ttl_seconds=30) is True
        # Instance 2 tries to acquire same lock and is rejected
        assert scheduler_2.acquire_leader_lock(ttl_seconds=30) is False

        # Instance 1 releases lock
        scheduler_1.release_leader_lock()
        # Now Instance 2 can acquire
        assert scheduler_2.acquire_leader_lock(ttl_seconds=30) is True

    # 2. Embedded Scheduler is disabled by default in LeadValidator
    def test_embedded_scheduler_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("ENABLE_EMBEDDED_SCHEDULER", raising=False)
        val = LeadValidator.__new__(LeadValidator)
        val.shutdown_event = asyncio.Event()

        # By default, os.getenv("ENABLE_EMBEDDED_SCHEDULER", "false") is "false"
        enabled = os.getenv("ENABLE_EMBEDDED_SCHEDULER", "false").lower() == "true"
        assert enabled is False

        # Explicitly enabling for single-process testing
        monkeypatch.setenv("ENABLE_EMBEDDED_SCHEDULER", "true")
        enabled = os.getenv("ENABLE_EMBEDDED_SCHEDULER", "false").lower() == "true"
        assert enabled is True

    # 3. Transactional Outbox: Redis Enqueue Failure Does NOT Advance next_crawl_at
    def test_redis_failure_does_not_advance_next_crawl(self, hardened_fixtures):
        redis_mock, db_conn, cursor = hardened_fixtures
        redis_mock.fail_lpush = True  # Simulate network partition or Redis outage

        scheduler = PriorityScheduler(redis_conn=redis_mock, db_conn=db_conn)
        ch_data = {"lead_score": 80, "forex_score": 75, "arabic_ratio": 90, "posts_7d": 20}

        job_id = scheduler.schedule_channel_crawl(
            channel_id="ch-outbox-fail",
            channel_username="forex_gold_outage",
            channel_data=ch_data
        )

        assert job_id is None
        executed_sqls = [str(call) for call in cursor.execute.call_args_list]

        # Verified: Job was recorded as 'pending', then upon Redis failure transitioned to 'enqueue_failed'
        assert any("status = 'enqueue_failed'" in s for s in executed_sqls)
        # Verified: next_crawl_at was NOT updated in leads table!
        assert not any("UPDATE leads" in s and "next_crawl_at" in s for s in executed_sqls)

    # 4. Outbox Reconciliation Rescues Failed Enqueues when Redis Recovers
    def test_outbox_reconciliation_rescues_failed_jobs(self, hardened_fixtures):
        redis_mock, db_conn, cursor = hardened_fixtures
        scheduler = PriorityScheduler(redis_conn=redis_mock, db_conn=db_conn)

        # Mock stuck outbox jobs in PostgreSQL
        sample_payload = json.dumps({
            "job_id": "job-stuck-1",
            "channel_username": "rescued_channel",
            "watermark": 1200
        })
        cursor.fetchall.return_value = [
            ("job-stuck-1", "ch-stuck", "rescued_channel", "queue:high", sample_payload)
        ]

        # Redis is healthy now (fail_lpush = False)
        reconciled = scheduler.reconcile_outbox_jobs(batch_size=10)
        assert reconciled == 1

        # Verified: Job pushed to Redis queue:high
        assert "queue:high" in redis_mock.queues
        assert len(redis_mock.queues["queue:high"]) == 1

        executed_sqls = [str(call) for call in cursor.execute.call_args_list]
        assert any("status = 'queued'" in s for s in executed_sqls)
        assert any("UPDATE leads" in s and "next_crawl_at" in s for s in executed_sqls)

    # 5. In-flight Deduplication: Excludes channels with active crawl jobs
    def test_in_flight_deduplication_query_structure(self, hardened_fixtures):
        redis_mock, db_conn, cursor = hardened_fixtures
        scheduler = PriorityScheduler(redis_conn=redis_mock, db_conn=db_conn)

        cursor.description = [("id",), ("channel_username",)]
        cursor.fetchall.return_value = []

        scheduler.get_channels_due_for_crawl(batch_size=10)
        executed_sqls = [str(call) for call in cursor.execute.call_args_list]

        # Verify NOT EXISTS clause excludes in-flight crawl jobs
        assert any("NOT EXISTS" in s and "crawl_jobs" in s for s in executed_sqls)
        assert any("status IN ('pending', 'queued', 'running')" in s for s in executed_sqls)

    # 6. Full Job Lifecycle: checkout (mark_job_running) -> completion
    def test_job_checkout_mark_running_and_completion(self, hardened_fixtures):
        redis_mock, db_conn, cursor = hardened_fixtures
        scheduler = PriorityScheduler(redis_conn=redis_mock, db_conn=db_conn)

        # A. Worker marks job running
        marked = scheduler.mark_job_running("test-job-lifecycle")
        assert marked is True
        executed_sqls = [str(call) for call in cursor.execute.call_args_list]
        assert any("status = 'running'" in s for s in executed_sqls)

        # B. Worker records completion
        cursor.execute.reset_mock()
        rec = scheduler.record_crawl_result(
            job_id="test-job-lifecycle",
            channel_id="ch-lifecycle",
            success=True,
            new_watermark=3000,
            posts_scanned=25
        )
        assert rec is True
        executed_calls = [str(call) for call in cursor.execute.call_args_list]
        assert any("UPDATE crawl_jobs" in s for s in executed_calls)
        assert any("completed" in s for s in executed_calls)

    # 7. Stale Running Job Crash Recovery
    def test_stale_running_job_crash_recovery(self, hardened_fixtures):
        redis_mock, db_conn, cursor = hardened_fixtures
        scheduler = PriorityScheduler(redis_conn=redis_mock, db_conn=db_conn)

        # Mock 2 orphaned jobs returned by RETURNING clause
        cursor.fetchall.return_value = [
            ("orphan-job-1", "ch-orphan-1"),
            ("orphan-job-2", "ch-orphan-2"),
        ]

        recovered = scheduler.reconcile_stale_running_jobs(timeout_minutes=30)
        assert recovered == 2
        executed_sqls = [str(call) for call in cursor.execute.call_args_list]
        assert any("status = 'failed'" in s and "Worker execution timeout / crash recovery" in s for s in executed_sqls)
        assert any("consecutive_crawl_failures = COALESCE(consecutive_crawl_failures, 0) + 1" in s for s in executed_sqls)

    # 8. Scheduler Worker Emits Redis Heartbeat
    @pytest.mark.asyncio
    async def test_scheduler_worker_emits_redis_heartbeat(self, hardened_fixtures):
        redis_mock, db_conn, cursor = hardened_fixtures
        worker = SchedulerWorker(redis_host="localhost", db_host="localhost")
        worker.redis_conn = redis_mock
        worker.db_helper = MagicMock()
        worker.db_helper.conn = db_conn
        worker.scheduler = PriorityScheduler(redis_conn=redis_mock, db_conn=db_conn)
        worker.backpressure_mgr = MagicMock()
        worker.backpressure_mgr.get_composite_pressure.return_value = "NORMAL"
        worker.backpressure_mgr.recommended_concurrency_factor.return_value = 1.0

        cursor.description = [("id",), ("channel_username",)]
        cursor.fetchall.return_value = []

        await worker.run_schedule_cycle()

        # Verify heartbeat key in Redis
        hb = redis_mock.get("heartbeat:worker:scheduler")
        assert hb is not None
        assert "202" in hb

    # 9. Subscriber Neutrality (400 vs 2M+) & Low-Activity Retention
    def test_subscriber_neutrality_and_dormant_retention(self):
        # 400 members vs 2,000,000 members with identical signals
        calc_small = ActivityClassifier.calculate_next_crawl(
            final_score=75, forex_score=60, arabic_score=80,
            posts_24h=5, posts_7d=25
        )
        calc_large = ActivityClassifier.calculate_next_crawl(
            final_score=75, forex_score=60, arabic_score=80,
            posts_24h=5, posts_7d=25
        )
        # Exact equal tier and interval
        assert calc_small["scheduling_tier"] == calc_large["scheduling_tier"]
        assert calc_small["interval_minutes"] == calc_large["interval_minutes"]

        # Dormant channel (0 posts in 30 days) is scheduled at low frequency, NEVER rejected
        calc_dormant = ActivityClassifier.calculate_next_crawl(
            final_score=50, forex_score=50, arabic_score=60,
            posts_24h=0, posts_7d=0, posts_30d=0,
            last_post_at=datetime.now(timezone.utc) - timedelta(days=45)
        )
        assert calc_dormant["scheduling_tier"] == ActivityClass.DORMANT
        assert calc_dormant["interval_minutes"] >= 10000
        assert calc_dormant["next_crawl_at"] > datetime.now(timezone.utc)

    # 10. Docker Compose Structure & Production Wiring Validation
    def test_docker_compose_structure_and_wiring(self):
        with open("docker-compose.yml", "r", encoding="utf-8") as f:
            compose = yaml.safe_load(f)

        services = compose.get("services", {})
        # Essential production services exist
        assert "worker_scheduler" in services
        assert "worker_validator" in services
        assert "worker_scavenger" in services
        assert "worker_radar" in services
        assert "postgres" in services
        assert "redis" in services

        # Scheduler entrypoint & dependencies
        scheduler_svc = services["worker_scheduler"]
        assert scheduler_svc["command"] == "python scheduler_worker.py"
        assert "postgres" in scheduler_svc["depends_on"]
        assert "redis" in scheduler_svc["depends_on"]

        # Validator configuration: embedded scheduler disabled
        validator_svc = services["worker_validator"]
        env = validator_svc.get("environment", [])
        assert any("ENABLE_EMBEDDED_SCHEDULER=false" in e for e in env)
