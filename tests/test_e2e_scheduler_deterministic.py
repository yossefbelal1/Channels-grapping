"""
tests/test_e2e_scheduler_deterministic.py
Deterministic End-to-End Simulation of the Complete Crawl Scheduling Pipeline.
"""

import json
import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from app.scheduler.activity_classifier import ActivityClassifier, ActivityClass
from app.scheduler.watermark_manager import WatermarkManager
from app.scheduler.priority_scheduler import PriorityScheduler
from scheduler_worker import SchedulerWorker
from validator import LeadValidator


class MockRedisE2E:
    def __init__(self):
        self.queues = {
            "queue:critical": [],
            "queue:high": [],
            "queue:normal": [],
            "queue:low": []
        }
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


@pytest.mark.asyncio
async def test_deterministic_e2e_scheduler_pipeline():
    """
    Simulate full cycle:
    1. Channel due in DB
    2. SchedulerWorker runs cycle -> enqueues job with watermark 500
    3. Validator pops job from queue
    4. Fetch messages returns newer messages [501, 505, 550]
    5. Watermark advanced to 550 in DB and Redis
    6. Crawl job completed and next_crawl_at updated
    """
    redis_mock = MockRedisE2E()
    db_mock = MagicMock()
    cursor_mock = MagicMock()
    db_mock.cursor.return_value.__enter__.return_value = cursor_mock

    # Step 1: Mock Due Channel in DB
    now = datetime.now(timezone.utc)
    cursor_mock.description = [
        ("id",), ("channel_username",), ("is_group",), ("lead_score",),
        ("forex_intent_score",), ("arabic_ratio",), ("activity_class",),
        ("next_crawl_at",), ("last_scanned_message_id",),
        ("consecutive_crawl_failures",), ("graph_importance_score",), ("last_activity",)
    ]
    cursor_mock.fetchall.return_value = [
        (
            "e2e-channel-id-1", "arabic_forex_signals", False, 85, 90, 85, "HOT",
            now - timedelta(minutes=15), 500, 0, 70, now - timedelta(hours=1)
        )
    ]

    # Step 2: SchedulerWorker processes cycle
    scheduler = PriorityScheduler(redis_conn=redis_mock, db_conn=db_mock)
    worker = SchedulerWorker(redis_host="localhost", db_host="localhost")
    worker.redis_conn = redis_mock
    worker.db_helper = MagicMock()
    worker.db_helper.conn = db_mock
    worker.scheduler = scheduler
    worker.backpressure_mgr = MagicMock()
    worker.backpressure_mgr.get_composite_pressure.return_value = "NORMAL"
    worker.backpressure_mgr.recommended_concurrency_factor.return_value = 1.0

    dispatched = await worker.run_schedule_cycle()
    assert dispatched == 1

    # Verify job in queue
    assert redis_mock.llen("queue:critical") == 1 or redis_mock.llen("queue:high") == 1
    target_q = "queue:critical" if redis_mock.llen("queue:critical") > 0 else "queue:high"
    raw_job = redis_mock.rpop(target_q)
    assert raw_job is not None
    job_payload = json.loads(raw_job)

    assert job_payload["channel_username"] == "arabic_forex_signals"
    assert job_payload["watermark"] == 500

    # Step 3 & 4: LeadValidator consumes and crawls with min_id=500
    validator = LeadValidator.__new__(LeadValidator)
    validator.redis_conn = redis_mock
    validator.db_helper = MagicMock()
    validator.db_helper.conn = db_mock
    validator.db_helper.is_blacklisted.return_value = False
    validator.db_helper.upsert_lead_v5.return_value = "e2e-channel-id-1"
    validator.db_helper.get_incoming_graph_count.return_value = 0
    validator.check_rescan_cooldown = MagicMock(return_value=False)
    validator.shutdown_event = asyncio.Event()
    validator.session_name = "e2e_session"
    validator.tg_manager = MagicMock()
    validator.scheduler = scheduler
    validator.watermark_mgr = WatermarkManager(redis_conn=redis_mock, db_conn=db_mock)

    # Mock new messages from Telethon with min_id=500
    class MockMessage:
        def __init__(self, msg_id, text, date):
            self.id = msg_id
            self.text = text
            self.date = date
            self.views = 250

    new_messages = [
        MockMessage(501, "توصية شراء الذهب XAUUSD هدف 2650", now - timedelta(hours=30)),
        MockMessage(502, "تحديث صفقة الذهب والنفط", now - timedelta(hours=24)),
        MockMessage(503, "إشارات فوركس يومية وتحليل السوق", now - timedelta(hours=12)),
        MockMessage(504, "فرصة بيع الاسترليني مقابل الدولار GBPUSD", now - timedelta(hours=2)),
        MockMessage(505, "تحليل فني لزوج اليورو دولار EURUSD", now - timedelta(minutes=20)),
        MockMessage(550, "إغلاق الصفقة على ربح +50 نقطة فوركس", now - timedelta(minutes=5)),
    ]

    captured_fetch = {}
    async def mock_fetch_messages_safe(entity, limit=50, min_id=0):
        captured_fetch["min_id"] = min_id
        captured_fetch["limit"] = limit
        return new_messages

    validator.fetch_messages_safe = mock_fetch_messages_safe
    validator.check_username_via_http = MagicMock(return_value={
        "status_code": 200, "exists": True, "is_channel": True,
        "title": "قناة توصيات فوركس الذهب", "description": "تداول العملات والذهب وتحليلات فوركس يومية", "member_count": 15000
    })

    from telethon.tl.types import Channel
    mock_entity = MagicMock(spec=Channel)
    mock_entity.id = 998877
    mock_entity.participants_count = 15000
    mock_entity.broadcast = True
    mock_entity.megagroup = False
    mock_entity.title = "قناة توصيات فوركس الذهب"
    mock_entity.username = "arabic_forex_signals"

    full_chat_mock = MagicMock()
    full_chat_mock.full_chat.about = "تداول العملات والذهب وتحليلات فوركس يومية"
    full_chat_mock.full_chat.participants_count = 15000

    async def mock_exec(sess, fn, shutdown_event=None):
        if "full" in getattr(fn, '__name__', '').lower():
            return full_chat_mock
        return mock_entity
    validator.tg_manager.execute_request = mock_exec

    # Process the job
    await validator.process_link(raw_job)

    # Step 5: Verification of pipeline execution
    # A. min_id watermark was sent to Telegram
    assert captured_fetch.get("min_id") == 500

    # B. Redis cache was updated to highest message id (550)
    assert redis_mock.get("watermark:channel:arabic_forex_signals") == "550"

    # C. Database received record_crawl_result call updating crawl_jobs
    executed_sqls = [str(call) for call in cursor_mock.execute.call_args_list]
    assert any("UPDATE crawl_jobs" in s for s in executed_sqls)
    assert any("status = %s" in s or "completed" in s for s in executed_sqls)
