"""
app/core/telegram_pool.py — Hardened Telegram Account Pool & Membership Lifecycle Manager

Production-Hardened Features:
- Account State Machine: HEALTHY, BUSY, COOLDOWN, FLOOD_WAIT, UNAVAILABLE, RECOVERING
- Workload Distribution: Least-loaded account selection considering active jobs and health
- Centralized Retry Policy: Exponential backoff with full jitter and permanent error classification
- Controlled Membership Lifecycle: TTL-style research slots, join tracking, churn prevention
"""

import os
import time
import math
import random
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


class AccountState:
    HEALTHY = "HEALTHY"
    BUSY = "BUSY"
    COOLDOWN = "COOLDOWN"
    FLOOD_WAIT = "FLOOD_WAIT"
    UNAVAILABLE = "UNAVAILABLE"
    RECOVERING = "RECOVERING"

    ALL = [HEALTHY, BUSY, COOLDOWN, FLOOD_WAIT, UNAVAILABLE, RECOVERING]
    ACTIVE = [HEALTHY, RECOVERING]


class RetryPolicy:
    """
    Centralized exponential backoff and jitter policy for Telegram API requests.
    """

    def __init__(
        self,
        base_backoff: float = 1.5,
        max_backoff: float = 30.0,
        max_retries: int = 3,
        jitter_factor: float = 0.25
    ):
        self.base_backoff = base_backoff
        self.max_backoff = max_backoff
        self.max_retries = max_retries
        self.jitter_factor = jitter_factor

    def compute_backoff(self, attempt: int) -> float:
        """
        Computes exponential backoff with full symmetric jitter.
        Formula: min(max_backoff, base * 2^attempt) * uniform(1 - jitter, 1 + jitter)
        """
        raw_backoff = min(self.max_backoff, self.base_backoff * (2.0 ** attempt))
        jitter_min = 1.0 - self.jitter_factor
        jitter_max = 1.0 + self.jitter_factor
        delay = raw_backoff * random.uniform(jitter_min, jitter_max)
        return round(delay, 2)

    @staticmethod
    def is_permanent_error(exc: Exception) -> bool:
        """
        Checks if an exception represents a permanent failure that should NOT be retried.
        """
        exc_str = str(exc).lower()
        exc_name = type(exc).__name__

        permanent_names = {
            "UsernameNotOccupiedError",
            "UsernameInvalidError",
            "ChannelPrivateError",
            "ChannelInvalidError",
            "ChatAdminRequiredError",
            "UserDeactivatedBanError",
            "AuthKeyUnregisteredError",
            "AuthKeyInvalidError",
            "SessionRevokedError",
            "ValueError",
            "TypeError"
        }
        if exc_name in permanent_names:
            return True

        if "not found" in exc_str or "private" in exc_str or "invalid" in exc_str:
            return True

        return False


class AccountPoolManager:
    """
    Manages session pool health telemetry, states, and smart load-balanced selection.
    """

    def __init__(self, redis_conn=None, db_conn=None):
        self.redis = redis_conn
        self.db = db_conn

    def _state_key(self, session_name: str) -> str:
        return f"account:pool:{session_name}:state"

    def _meta_key(self, session_name: str) -> str:
        return f"account:pool:{session_name}:meta"

    def get_state(self, session_name: str) -> str:
        """Returns the current state of an account session."""
        if not self.redis:
            return AccountState.HEALTHY
        try:
            val = self.redis.get(self._state_key(session_name))
            if val:
                return val.decode("utf-8") if isinstance(val, bytes) else str(val)
        except Exception as err:
            logger.debug(f"Redis get_state error: {err}")
        return AccountState.HEALTHY

    def set_state(self, session_name: str, state: str, ttl_seconds: Optional[int] = None):
        """Sets the state of an account session with optional TTL."""
        if not self.redis or state not in AccountState.ALL:
            return
        try:
            key = self._state_key(session_name)
            if ttl_seconds and ttl_seconds > 0:
                self.redis.setex(key, ttl_seconds, state)
            else:
                self.redis.set(key, state)
        except Exception as err:
            logger.debug(f"Redis set_state error: {err}")

    def record_request_start(self, session_name: str):
        """Increments active jobs and updates last_used_at."""
        if not self.redis:
            return
        try:
            pipe = self.redis.pipeline()
            pipe.hincrby(self._meta_key(session_name), "active_jobs", 1)
            pipe.hincrby(self._meta_key(session_name), "request_count", 1)
            pipe.hset(self._meta_key(session_name), "last_used_at", int(time.time()))
            pipe.execute()
        except Exception as err:
            logger.debug(f"record_request_start error: {err}")

    def record_request_end(self, session_name: str, success: bool, error_type: Optional[str] = None):
        """Decrements active jobs and tracks success/failure counters."""
        if not self.redis:
            return
        try:
            pipe = self.redis.pipeline()
            pipe.hincrby(self._meta_key(session_name), "active_jobs", -1)
            if success:
                pipe.hincrby(self._meta_key(session_name), "success_count", 1)
                pipe.hset(self._meta_key(session_name), "recent_error_count", 0)
            else:
                pipe.hincrby(self._meta_key(session_name), "failure_count", 1)
                pipe.hincrby(self._meta_key(session_name), "recent_error_count", 1)
                if error_type:
                    pipe.hset(self._meta_key(session_name), "last_error_type", error_type)
            pipe.execute()
        except Exception as err:
            logger.debug(f"record_request_end error: {err}")

    def record_flood_wait(self, session_name: str, wait_seconds: int):
        """Sets FLOOD_WAIT state and records cooldown timestamp."""
        ttl = wait_seconds + 30 # 30s safety margin
        self.set_state(session_name, AccountState.FLOOD_WAIT, ttl_seconds=ttl)
        if self.redis:
            try:
                self.redis.setex(f"account:pool:{session_name}:flood_wait_until", ttl, int(time.time() + wait_seconds))
            except Exception:
                pass

    def get_telemetry(self, session_name: str) -> Dict[str, Any]:
        """Retrieves full telemetry dictionary for an account."""
        state = self.get_state(session_name)
        meta: Dict[str, Any] = {}
        if self.redis:
            try:
                raw_meta = self.redis.hgetall(self._meta_key(session_name))
                for k, v in (raw_meta or {}).items():
                    k_str = k.decode() if isinstance(k, bytes) else str(k)
                    v_str = v.decode() if isinstance(v, bytes) else str(v)
                    try:
                        meta[k_str] = int(v_str)
                    except ValueError:
                        meta[k_str] = v_str
            except Exception:
                pass

        return {
            "session_name": session_name,
            "state": state,
            "active_jobs": max(0, int(meta.get("active_jobs", 0))),
            "request_count": int(meta.get("request_count", 0)),
            "success_count": int(meta.get("success_count", 0)),
            "failure_count": int(meta.get("failure_count", 0)),
            "recent_error_count": int(meta.get("recent_error_count", 0)),
            "last_used_at": meta.get("last_used_at"),
            "last_error_type": meta.get("last_error_type")
        }

    def select_least_loaded(self, candidate_sessions: List[str]) -> Optional[str]:
        """
        Chooses the optimal session:
        1. Prefers HEALTHY or RECOVERING states
        2. Lowest active_jobs
        3. Lowest failure count / recent errors
        4. Longest time since last_used_at
        """
        if not candidate_sessions:
            return None

        scored_candidates = []
        now = time.time()

        for s_name in candidate_sessions:
            telemetry = self.get_telemetry(s_name)
            state = telemetry["state"]

            # Exclude unavailable or flood-waiting accounts
            if state in [AccountState.FLOOD_WAIT, AccountState.UNAVAILABLE, AccountState.COOLDOWN]:
                continue

            active_jobs = telemetry["active_jobs"]
            recent_errors = telemetry["recent_error_count"]
            last_used = telemetry["last_used_at"] or 0
            idle_seconds = max(0, now - last_used)

            # Lower load_score is better
            load_score = (active_jobs * 100) + (recent_errors * 20) - min(50, idle_seconds)
            if state == AccountState.RECOVERING:
                load_score += 50 # slight penalty during recovery

            scored_candidates.append((load_score, s_name))

        if not scored_candidates:
            # If all are cooling or busy, pick the first non-unavailable candidate
            return candidate_sessions[0] if candidate_sessions else None

        scored_candidates.sort(key=lambda x: x[0])
        return scored_candidates[0][1]


class MembershipManager:
    """
    Controlled channel membership manager with TTL-based research slots and churn prevention.
    """

    def __init__(self, db_conn=None, redis_conn=None):
        self.db = db_conn
        self.redis = redis_conn

    def record_join(
        self,
        channel_id: str,
        account_session: str,
        channel_username: Optional[str] = None,
        ttl_hours: int = 24,
        reason: str = "deep_scan"
    ) -> bool:
        """
        Records a channel join in PostgreSQL with an expiration timestamp for deep scanning.
        """
        if not self.db:
            return False

        now = datetime.now(timezone.utc)
        leave_at = now + timedelta(hours=ttl_hours)

        try:
            with self.db.cursor() as cur:
                cur.execute("""
                    INSERT INTO channel_memberships (
                        channel_id, channel_username, account_session,
                        joined_at, leave_at, membership_reason, current_state
                    ) VALUES (%s, %s, %s, %s, %s, %s, 'ACTIVE');
                """, (str(channel_id), channel_username, account_session, now, leave_at, reason))
            self.db.commit()
            return True
        except Exception as err:
            logger.warning(f"Failed to record membership join for {channel_id}: {err}")
            try:
                self.db.rollback()
            except Exception:
                pass
            return False

    def schedule_leave(self, channel_id: str, account_session: str) -> bool:
        """
        Marks a membership as SCHEDULED_LEAVE so the background worker leaves cleanly.
        """
        if not self.db:
            return False

        try:
            with self.db.cursor() as cur:
                cur.execute("""
                    UPDATE channel_memberships
                    SET current_state = 'SCHEDULED_LEAVE',
                        updated_at = NOW()
                    WHERE channel_id = %s AND account_session = %s AND current_state = 'ACTIVE';
                """, (str(channel_id), account_session))
            self.db.commit()
            return True
        except Exception as err:
            logger.warning(f"Failed to schedule membership leave for {channel_id}: {err}")
            try:
                self.db.rollback()
            except Exception:
                pass
            return False

    def get_expired_memberships(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Retrieves memberships whose TTL has expired or that are SCHEDULED_LEAVE.
        """
        if not self.db:
            return []

        try:
            with self.db.cursor() as cur:
                cur.execute("""
                    SELECT id, channel_id, channel_username, account_session, leave_at
                    FROM channel_memberships
                    WHERE current_state IN ('ACTIVE', 'SCHEDULED_LEAVE')
                      AND (leave_at <= NOW() OR current_state = 'SCHEDULED_LEAVE')
                    ORDER BY leave_at ASC
                    LIMIT %s;
                """, (limit,))
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as err:
            logger.warning(f"Failed to fetch expired memberships: {err}")
            return []

    def mark_left(self, membership_id: int) -> bool:
        """Marks a membership as LEFT after executing LeaveChannelRequest."""
        if not self.db:
            return False

        try:
            with self.db.cursor() as cur:
                cur.execute("""
                    UPDATE channel_memberships
                    SET current_state = 'LEFT',
                        updated_at = NOW()
                    WHERE id = %s;
                """, (membership_id,))
            self.db.commit()
            return True
        except Exception as err:
            logger.warning(f"Failed to mark membership {membership_id} as LEFT: {err}")
            try:
                self.db.rollback()
            except Exception:
                pass
            return False
