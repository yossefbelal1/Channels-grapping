"""
tests/test_scheduler_worker_integration.py
Comprehensive Integration Tests for PriorityScheduler, WatermarkManager, and Worker Runtime.
Validates Points A through L:
  A. Due channel selection from DB
  B. Crawl job creation in crawl_jobs and Redis queue enqueue
  C. Queue payload attributes (priority, watermark, scan_depth)
  D. Worker unpacks watermark from crawl payload
  E. Incremental crawl passes min_id=watermark to fetch_messages_safe
  F. Successful crawl updates watermark in DB and Redis
  G. next_crawl_at updates dynamically based on channel activity & value
  H. Low-activity channels scheduled with longer interval, NEVER rejected
  I. High-value channels get higher priority (queue:critical / queue:high)
  J. Failures trigger exponential backoff multiplier
  K. Restart/crash recovery for pending jobs
  L. Verification that all priority queues have active consumers
"""

import json
import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

from app.scheduler.activity_classifier import ActivityClassifier, ActivityClass, ScanDepthTier
from app.scheduler.watermark_manager import WatermarkManager
from app.scheduler.priority_scheduler import PriorityScheduler
from scheduler_worker import SchedulerWorker
from validator import LeadValidator


class TestSchedulerWorkerIntegration:

    @pytest.fixture
    def mock_redis(self):
        storage = {}
        class MockRedis:
            def __init__(self):
                self.queues = {}
                self.kv = {}
            def lpush(self, key, val):
                self.queues.setdefault(key, []).append(val)
                return len(self.queues[key])
            def rpush(self, key, val):
                self.queues.setdefault(key, []).insert(0, val)
                return len(self.queues[key])
            def blpop(self, keys, timeout=0):
                for k in keys:
                    if self.queues.get(k):
                        return (k, self.queues[k].pop(0))
                return None
            def rpop(self, key):
                if self.queues.get(key):
                    return self.queues[key].pop()
                return None
            def get(self, key):
                return self.kv.get(key)
            def set(self, key, val, ex=None):
                self.kv[key] = str(val)
                return True
            def setex(self, key, time_s, val):
                self.kv[key] = str(val)
                return True
            def llen(self, key):
                return len(self.queues.get(key, []))
            def sismember(self, key, member):
                return False
            def sadd(self, key, member):
                return True
            def ping(self):
                return True
        return MockRedis()

    @pytest.fixture
    def mock_db(self):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        return conn, cursor

    # ── Point A: Due channel selected from DB ──────────────────────────────────
    def test_point_a_due_channels_selected(self, mock_redis, mock_db):
        conn, cursor = mock_db
        now = datetime.now(timezone.utc)
        cursor.description = [
            ("id",), ("channel_username",), ("is_group",), ("lead_score",),
            ("forex_intent_score",), ("arabic_ratio",), ("activity_class",),
            ("next_crawl_at",), ("last_scanned_message_id",),
            ("consecutive_crawl_failures",), ("graph_importance_score",), ("last_activity",)
        ]
        cursor.fetchall.return_value = [
            (
                "ch-1", "arabic_forex_vip", False, 85, 90, 85, "HOT",
                now - timedelta(minutes=5), 1040, 0, 75, now - timedelta(hours=2)
            )
        ]

        scheduler = PriorityScheduler(redis_conn=mock_redis, db_conn=conn)
        due = scheduler.get_channels_due_for_crawl(batch_size=10)

        assert len(due) == 1
        assert due[0]["channel_username"] == "arabic_forex_vip"
        assert due[0]["lead_score"] == 85
        assert due[0]["last_scanned_message_id"] == 1040

    # ── Point B & C: Scheduler creates crawl job and enqueues to Redis with attributes ──
    def test_point_b_and_c_job_creation_and_payload(self, mock_redis, mock_db):
        conn, cursor = mock_db
        scheduler = PriorityScheduler(redis_conn=mock_redis, db_conn=conn)

        channel_data = {
            "lead_score": 85,
            "forex_intent_score": 90,
            "arabic_ratio": 80,
            "posts_24h": 8,
            "posts_7d": 40,
            "last_scanned_message_id": 2500,
            "graph_importance_score": 70
        }

        job_id = scheduler.schedule_channel_crawl(
            channel_id="ch-vip",
            channel_username="forex_signals_gold",
            channel_data=channel_data
        )

        assert job_id is not None
        assert "queue:critical" in mock_redis.queues or "queue:high" in mock_redis.queues
        q_name = "queue:critical" if "queue:critical" in mock_redis.queues else "queue:high"
        raw_payload = mock_redis.queues[q_name][0]
        payload = json.loads(raw_payload)

        assert payload["job_id"] == job_id
        assert payload["channel_username"] == "forex_signals_gold"
        assert payload["watermark"] == 2500
        assert payload["scan_depth_tier"] in [ScanDepthTier.INCREMENTAL, ScanDepthTier.DEEP]
        assert payload["max_posts_budget"] > 0
        assert payload["source"] == "priority_scheduler"

        sql_calls = [str(call) for call in cursor.execute.call_args_list]
        assert any("INSERT INTO crawl_jobs" in call for call in sql_calls)

    # ── Point D & E: Worker consumes job, unpacks watermark and passes min_id ───
    @pytest.mark.asyncio
    async def test_point_d_and_e_worker_unpacks_watermark_and_passes_min_id(self, mock_redis, mock_db):
        conn, cursor = mock_db
        validator = LeadValidator.__new__(LeadValidator)
        validator.redis_conn = mock_redis
        validator.db_helper = MagicMock()
        validator.db_helper.conn = conn
        validator.db_helper.is_blacklisted.return_value = False
        validator.check_rescan_cooldown = MagicMock(return_value=False)
        validator.shutdown_event = asyncio.Event()
        validator.session_name = "test_sess"
        validator.tg_manager = MagicMock()
        validator.scheduler = PriorityScheduler(redis_conn=mock_redis, db_conn=conn)
        validator.watermark_mgr = WatermarkManager(redis_conn=mock_redis, db_conn=conn)

        captured_fetch_kwargs = {}
        async def mock_fetch_messages_safe(entity, limit=50, min_id=0):
            captured_fetch_kwargs["limit"] = limit
            captured_fetch_kwargs["min_id"] = min_id
            return []

        validator.fetch_messages_safe = mock_fetch_messages_safe
        validator.check_username_via_http = MagicMock(return_value={
            "status_code": 200, "exists": True, "is_channel": True,
            "title": "توصيات فوركس الذهب", "description": "تداول العملات والذهب فوركس", "member_count": 5000
        })

        from telethon.tl.types import Channel
        mock_entity = MagicMock(spec=Channel)
        mock_entity.id = 12345
        mock_entity.participants_count = 5000
        mock_entity.broadcast = True
        mock_entity.megagroup = False
        mock_entity.title = "قناة توصيات فوركس الذهب"
        mock_entity.username = "arabic_forex_trader"

        full_chat_mock = MagicMock()
        full_chat_mock.full_chat.about = "توصيات فوركس يومية وتحليل الذهب"
        full_chat_mock.full_chat.participants_count = 5000

        async def mock_exec_req(sess, fn, shutdown_event=None):
            if "full" in getattr(fn, '__name__', '').lower():
                return full_chat_mock
            return mock_entity
        validator.tg_manager.execute_request = mock_exec_req

        job_payload = {
            "job_id": "test-job-uuid",
            "link": "https://t.me/arabic_forex_trader",
            "channel_username": "arabic_forex_trader",
            "source": "priority_scheduler",
            "watermark": 4200,
            "max_posts_budget": 75,
            "scan_depth_tier": "incremental"
        }

        await validator.process_link(json.dumps(job_payload))

        assert captured_fetch_kwargs.get("min_id") == 4200
        assert captured_fetch_kwargs.get("limit") == 75

    # ── Point F: Successful crawl updates watermark in DB and Redis ─────────────
    def test_point_f_watermark_update(self, mock_redis, mock_db):
        conn, cursor = mock_db
        mgr = WatermarkManager(redis_conn=mock_redis, db_conn=conn)

        updated_wm = mgr.update_watermark(channel_id="ch_99", new_watermark=1550, channel_username="forex_saudi")

        assert updated_wm == 1550
        assert mock_redis.get("watermark:channel:ch_99") == "1550"
        sql_calls = [str(call) for call in cursor.execute.call_args_list]
        assert any("GREATEST(COALESCE(last_scanned_message_id, 0)" in call for call in sql_calls)

    # ── Point G: next_crawl_at updates dynamically ──────────────────────────────
    def test_point_g_dynamic_schedule_calculation(self):
        now = datetime.now(timezone.utc)
        res_hot = ActivityClassifier.calculate_next_crawl(
            final_score=80,
            forex_score=85,
            posts_24h=12,
            posts_7d=60,
            has_watermark=True
        )
        res_normal = ActivityClassifier.calculate_next_crawl(
            final_score=35,
            forex_score=20,
            posts_24h=0,
            posts_7d=4,
            has_watermark=True
        )

        assert res_hot["interval_minutes"] < res_normal["interval_minutes"]
        assert res_hot["next_crawl_at"] < res_normal["next_crawl_at"]

    # ── Point H: Low activity channels scheduled later, never rejected ──────────
    def test_point_h_low_activity_scheduled_never_rejected(self):
        now = datetime.now(timezone.utc)
        dormant = ActivityClassifier.calculate_next_crawl(
            final_score=50,
            forex_score=60,
            posts_24h=0,
            posts_7d=0,
            posts_30d=0,
            last_post_at=now - timedelta(days=60)
        )
        assert dormant["scheduling_tier"] == ActivityClass.DORMANT
        assert dormant["interval_minutes"] >= 14400
        assert dormant["next_crawl_at"] > now

    # ── Point I: High-value channels get higher priority ────────────────────────
    def test_point_i_high_value_priority_tier(self, mock_redis, mock_db):
        conn, cursor = mock_db
        scheduler = PriorityScheduler(redis_conn=mock_redis, db_conn=conn)

        high_val_data = {
            "lead_score": 90,
            "forex_score": 95,
            "arabic_score": 90,
            "posts_24h": 10,
            "posts_7d": 45,
            "graph_importance_score": 80
        }
        scheduler.schedule_channel_crawl(
            channel_id="ch-top",
            channel_username="top_arabic_forex",
            channel_data=high_val_data
        )

        low_val_data = {
            "lead_score": 15,
            "forex_score": 10,
            "arabic_score": 20,
            "posts_24h": 0,
            "posts_7d": 1,
            "graph_importance_score": 5
        }
        scheduler.schedule_channel_crawl(
            channel_id="ch-low",
            channel_username="low_channel",
            channel_data=low_val_data
        )

        assert "queue:critical" in mock_redis.queues or "queue:high" in mock_redis.queues
        assert "queue:normal" in mock_redis.queues or "queue:low" in mock_redis.queues

    # ── Point J: Failures increase failure backoff ──────────────────────────────
    def test_point_j_failure_backoff(self):
        base_calc = ActivityClassifier.calculate_next_crawl(
            final_score=60,
            forex_score=50,
            consecutive_failures=0
        )
        backoff_calc = ActivityClassifier.calculate_next_crawl(
            final_score=60,
            forex_score=50,
            consecutive_failures=4
        )
        assert backoff_calc["interval_minutes"] > base_calc["interval_minutes"]

    # ── Point K: Restart / crash recovery ───────────────────────────────────────
    def test_point_k_scheduler_recovery_on_startup(self, mock_redis, mock_db):
        conn, cursor = mock_db
        cursor.description = [
            ("id",), ("channel_username",), ("is_group",), ("lead_score",),
            ("forex_intent_score",), ("arabic_ratio",), ("activity_class",),
            ("next_crawl_at",), ("last_scanned_message_id",),
            ("consecutive_crawl_failures",), ("graph_importance_score",), ("last_activity",)
        ]
        cursor.fetchall.return_value = [
            ("rec-1", "recovered_forex", False, 70, 75, 80, "WARM", None, 500, 0, 50, None)
        ]

        worker = SchedulerWorker(
            redis_host="localhost",
            db_host="localhost",
            poll_interval=10,
            batch_size=5
        )
        worker.redis_conn = mock_redis
        worker.db_helper = MagicMock()
        worker.db_helper.conn = conn
        worker.scheduler = PriorityScheduler(redis_conn=mock_redis, db_conn=conn)
        worker.backpressure_mgr = MagicMock()
        worker.backpressure_mgr.get_composite_pressure.return_value = "NORMAL"
        worker.backpressure_mgr.recommended_concurrency_factor.return_value = 1.0

        dispatched = asyncio.run(worker.run_schedule_cycle())
        assert dispatched == 1
        assert any(len(q) > 0 for q in mock_redis.queues.values())

    # ── Point L: All priority queues have an active consumer ────────────────────
    def test_point_l_priority_queues_have_consumers(self):
        import inspect
        source = inspect.getsource(LeadValidator.start)
        assert '["queue:critical", "queue:high", "queue:normal", "queue:low"]' in source
