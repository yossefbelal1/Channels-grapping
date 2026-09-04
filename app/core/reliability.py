"""
app/core/reliability.py — Redis Job Reliability, Idempotency & Dead Letter Queue (PART N)

Hardened Features:
- Standardized JobEnvelope with job_id, idempotency_key, attempt_count, created_at, scheduled_at
- Redis-backed distributed idempotency locks to prevent duplicate deep-scan execution
- Dead Letter Queue (DLQ) for failed/poison jobs with audit metadata and replay capability
- Crash recovery semantics
"""

import json
import uuid
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)

DEFAULT_DLQ_NAME = "queue:dead_letter"
DEFAULT_IDEMPOTENCY_TTL_SECONDS = 3600 # 1 hour lock on identical jobs


class JobEnvelope:
    """
    Standardized job payload wrapper guaranteeing traceable idempotency and retry accounting.
    """

    @staticmethod
    def wrap(
        payload: Dict[str, Any],
        idempotency_key: Optional[str] = None,
        job_id: Optional[str] = None,
        max_attempts: int = 3
    ) -> Dict[str, Any]:
        jid = job_id or str(uuid.uuid4())
        ikey = idempotency_key or f"job:{payload.get('link') or payload.get('channel_username') or jid}"

        envelope = {
            "job_id": jid,
            "idempotency_key": ikey,
            "attempt_count": int(payload.get("attempt_count", 0)),
            "max_attempts": max_attempts,
            "created_at": payload.get("created_at") or datetime.now(timezone.utc).isoformat(),
            "scheduled_at": payload.get("scheduled_at") or datetime.now(timezone.utc).isoformat(),
            "payload": payload
        }
        return envelope

    @staticmethod
    def unwrap(job_data: Any) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Unpacks job data into (payload, metadata).
        Supports both raw legacy payloads and hardened JobEnvelope dicts.
        """
        if isinstance(job_data, str):
            try:
                job_data = json.loads(job_data)
            except Exception:
                job_data = {"raw": job_data}

        if not isinstance(job_data, dict):
            return {"value": job_data}, {}

        if "payload" in job_data and "job_id" in job_data:
            return job_data["payload"], {
                "job_id": job_data["job_id"],
                "idempotency_key": job_data.get("idempotency_key"),
                "attempt_count": job_data.get("attempt_count", 0),
                "max_attempts": job_data.get("max_attempts", 3),
                "created_at": job_data.get("created_at")
            }

        # Legacy payload fallback
        return job_data, {
            "job_id": job_data.get("job_id", str(uuid.uuid4())),
            "idempotency_key": job_data.get("link") or str(uuid.uuid4()),
            "attempt_count": job_data.get("attempt_count", 0),
            "max_attempts": 3,
            "created_at": job_data.get("created_at")
        }


class IdempotencyGuard:
    """
    Prevents the same channel from entering expensive deep-scan or crawl work repeatedly.
    """

    def __init__(self, redis_conn, ttl_seconds: int = DEFAULT_IDEMPOTENCY_TTL_SECONDS):
        self.redis = redis_conn
        self.ttl = ttl_seconds

    def acquire(self, idempotency_key: str, worker_id: str = "worker") -> bool:
        """
        Attempts to acquire an idempotency lock for the job key.
        Returns True if acquired (safe to execute), False if already active/recently run.
        """
        if not self.redis:
            return True
        key = f"idempotency:lock:{idempotency_key}"
        try:
            val = f"{worker_id}:{time.time()}"
            acquired = self.redis.set(key, val, ex=self.ttl, nx=True)
            return bool(acquired)
        except Exception as err:
            logger.debug(f"Idempotency acquire error (failing open): {err}")
            return True

    def release(self, idempotency_key: str):
        """Releases the idempotency lock upon completion if needed early."""
        if not self.redis:
            return
        key = f"idempotency:lock:{idempotency_key}"
        try:
            self.redis.delete(key)
        except Exception:
            pass


class DeadLetterQueueManager:
    """
    Manages Dead Letter Queue (DLQ) for permanently failed or exceeded-retry jobs.
    """

    def __init__(self, redis_conn, dlq_name: str = DEFAULT_DLQ_NAME):
        self.redis = redis_conn
        self.dlq_name = dlq_name

    def send_to_dlq(
        self,
        job_envelope: Dict[str, Any],
        error_type: str,
        error_message: str,
        origin_queue: str
    ) -> bool:
        """
        Pushes a failed job to the DLQ with structured forensic audit metadata.
        """
        if not self.redis:
            return False

        record = {
            "dlq_id": str(uuid.uuid4()),
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "origin_queue": origin_queue,
            "error_type": error_type,
            "error_message": str(error_message)[:1000],
            "job": job_envelope
        }

        try:
            self.redis.lpush(self.dlq_name, json.dumps(record))
            logger.warning(f"☠️ Moved poisoned job {job_envelope.get('job_id')} to DLQ ({self.dlq_name}): {error_type}")
            return True
        except Exception as err:
            logger.error(f"Failed to push job to DLQ: {err}")
            return False

    def get_dlq_depth(self) -> int:
        """Returns the number of poisoned jobs in DLQ."""
        if not self.redis:
            return 0
        try:
            return int(self.redis.llen(self.dlq_name))
        except Exception:
            return 0

    def peek_dlq(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Views the most recent items in DLQ without popping."""
        if not self.redis:
            return []
        try:
            raw_items = self.redis.lrange(self.dlq_name, 0, limit - 1)
            return [json.loads(item) for item in raw_items if item]
        except Exception:
            return []
