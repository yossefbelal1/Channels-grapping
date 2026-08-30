"""
app/outreach/metrics.py — Outreach Observability Metrics Collector

Records metrics to both Redis (real-time counters) and PostgreSQL
(historical outreach_metrics table) for dashboards and trend analysis.

Usage:
    metrics = OutreachMetrics(redis_conn, db_conn)
    metrics.record_attempt(session_name, campaign_id)
    metrics.record_success(session_name, campaign_id)
    metrics.record_failure(session_name, campaign_id, error_type)
    metrics.record_flood_wait(session_name, wait_seconds)
    
    snapshot = metrics.get_dashboard_snapshot()
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class OutreachMetrics:
    """
    Observability metrics collector for the outreach pipeline.
    
    Real-time counters are stored in Redis with hourly TTLs.
    Historical data is periodically flushed to PostgreSQL.
    """

    # Redis key prefixes
    PREFIX = "metrics:outreach"

    def __init__(self, redis_conn, db_conn=None):
        """
        Initialize metrics collector.
        
        Args:
            redis_conn: Redis connection for real-time counters.
            db_conn: Optional PostgreSQL connection for historical persistence.
        """
        self.redis_conn = redis_conn
        self.db_conn = db_conn

    # ── Counter Operations ────────────────────────────────────────────────

    def _incr(self, key: str, amount: int = 1, ttl: int = 7200) -> None:
        """Safely increment a Redis counter with TTL."""
        try:
            full_key = f"{self.PREFIX}:{key}"
            pipe = self.redis_conn.pipeline(transaction=False)
            pipe.incr(full_key, amount)
            pipe.expire(full_key, ttl)
            pipe.execute()
        except Exception as e:
            logger.warning(f"Metrics: Failed to increment {key}: {e}")

    def _get_counter(self, key: str) -> int:
        """Safely read a Redis counter."""
        try:
            val = self.redis_conn.get(f"{self.PREFIX}:{key}")
            return int(val) if val else 0
        except Exception as e:
            logger.warning(f"Metrics: Failed to read {key}: {e}")
            return 0

    def _set_gauge(self, key: str, value: float, ttl: int = 300) -> None:
        """Safely set a Redis gauge value."""
        try:
            self.redis_conn.set(f"{self.PREFIX}:{key}", str(value), ex=ttl)
        except Exception as e:
            logger.warning(f"Metrics: Failed to set gauge {key}: {e}")

    # ── Recording Methods ─────────────────────────────────────────────────

    def record_attempt(self, session_name: str = "", campaign_id: str = "") -> None:
        """Record an outreach send attempt."""
        self._incr("attempts_total")
        if session_name:
            self._incr(f"attempts:{session_name}")

    def record_success(self, session_name: str = "", campaign_id: str = "") -> None:
        """Record a successful outreach delivery."""
        self._incr("success_total")
        if session_name:
            self._incr(f"success:{session_name}")

    def record_failure(self, session_name: str = "", campaign_id: str = "",
                       error_type: str = "unknown") -> None:
        """Record a failed outreach delivery."""
        self._incr("failures_total")
        if session_name:
            self._incr(f"failures:{session_name}")
        self._incr(f"failures_by_type:{error_type}")

    def record_flood_wait(self, session_name: str, wait_seconds: int) -> None:
        """Record a FloodWait event."""
        self._incr("flood_wait_total")
        self._incr("flood_wait_seconds_total", amount=wait_seconds)
        if session_name:
            self._incr(f"flood_wait:{session_name}")

    def record_retry(self, lead_id: str = "") -> None:
        """Record a retry attempt."""
        self._incr("retry_total")

    def record_unknown_delivery(self) -> None:
        """Record a delivery with unknown outcome."""
        self._incr("unknown_delivery_total")

    def record_skip(self, reason: str = "unknown") -> None:
        """Record a skipped delivery."""
        self._incr("skipped_total")
        self._incr(f"skipped_by_reason:{reason}")

    def record_eligibility_check(self, result: str) -> None:
        """Record eligibility check result."""
        self._incr(f"eligibility:{result}")

    def record_risk_level(self, level: str) -> None:
        """Record risk level assignment."""
        self._incr(f"risk_level:{level}")

    def record_circuit_breaker_trip(self, breaker_type: str, identifier: str) -> None:
        """Record a circuit breaker activation."""
        self._incr(f"circuit_breaker_trips:{breaker_type}")

    def record_reconciliation(self, action: str) -> None:
        """Record a reconciliation action."""
        self._incr(f"reconciliation:{action}")

    def record_dry_run_decision(self) -> None:
        """Record a dry-run decision (would-have-sent)."""
        self._incr("dry_run_decisions")

    # ── Queue Depth Gauges ────────────────────────────────────────────────

    def update_queue_depths(self) -> Dict[str, int]:
        """
        Read and record current queue depths as gauge values.
        
        Returns:
            Dict with queue name -> depth mappings.
        """
        depths = {}
        try:
            queue_keys = {
                'outreach_high': 'outreach:high',
                'outreach_normal': 'outreach:normal',
                'outreach_low': 'outreach:low',
                'validation_critical': 'queue:critical',
                'validation_high': 'queue:high',
                'validation_normal': 'queue:normal',
                'validation_low': 'queue:low',
            }
            for label, redis_key in queue_keys.items():
                depth = self.redis_conn.llen(redis_key) or 0
                depths[label] = depth
                self._set_gauge(f"queue_depth:{label}", depth)

            total_outreach = sum(depths.get(k, 0) for k in
                                 ['outreach_high', 'outreach_normal', 'outreach_low'])
            self._set_gauge("queue_depth:outreach_total", total_outreach)

            total_validation = sum(depths.get(k, 0) for k in
                                   ['validation_critical', 'validation_high',
                                    'validation_normal', 'validation_low'])
            self._set_gauge("queue_depth:validation_total", total_validation)

        except Exception as e:
            logger.warning(f"Metrics: Failed to update queue depths: {e}")

        return depths

    # ── Account Health Gauges ─────────────────────────────────────────────

    def update_account_health_gauges(self, account_states: Dict[str, str]) -> None:
        """
        Record current account health distribution.
        
        Args:
            account_states: Dict mapping session_name -> state string.
        """
        try:
            state_counts: Dict[str, int] = {}
            for session_name, state in account_states.items():
                state_counts[state] = state_counts.get(state, 0) + 1
                self._set_gauge(f"account_state:{session_name}", 1 if state == 'HEALTHY' else 0)

            for state, count in state_counts.items():
                self._set_gauge(f"accounts_in_state:{state}", count)

        except Exception as e:
            logger.warning(f"Metrics: Failed to update account health gauges: {e}")

    # ── Dashboard Snapshot ────────────────────────────────────────────────

    def get_dashboard_snapshot(self) -> Dict[str, Any]:
        """
        Get a complete metrics snapshot for the dashboard.
        
        Returns a dict with all current metric values.
        """
        snapshot = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'counters': {},
            'queues': {},
            'rates': {},
        }

        try:
            # Core counters
            counter_keys = [
                'attempts_total', 'success_total', 'failures_total',
                'flood_wait_total', 'flood_wait_seconds_total',
                'retry_total', 'unknown_delivery_total',
                'skipped_total', 'dry_run_decisions',
            ]
            for key in counter_keys:
                snapshot['counters'][key] = self._get_counter(key)

            # Success rate
            attempts = snapshot['counters'].get('attempts_total', 0)
            successes = snapshot['counters'].get('success_total', 0)
            if attempts > 0:
                snapshot['rates']['success_rate'] = round(successes / attempts, 4)
                snapshot['rates']['failure_rate'] = round(
                    snapshot['counters'].get('failures_total', 0) / attempts, 4
                )
            else:
                snapshot['rates']['success_rate'] = 0.0
                snapshot['rates']['failure_rate'] = 0.0

            # Queue depths
            snapshot['queues'] = self.update_queue_depths()

        except Exception as e:
            logger.warning(f"Metrics: Failed to build dashboard snapshot: {e}")
            snapshot['error'] = str(e)

        return snapshot

    # ── Historical Persistence ────────────────────────────────────────────

    def persist_to_db(self) -> int:
        """
        Flush current counter values to PostgreSQL outreach_metrics table
        for historical analysis.
        
        Returns number of metrics persisted.
        """
        if not self.db_conn:
            return 0

        persisted = 0
        now = datetime.now(timezone.utc)

        try:
            snapshot = self.get_dashboard_snapshot()
            cursor = self.db_conn.cursor()

            # Persist counters
            for metric_name, value in snapshot.get('counters', {}).items():
                cursor.execute(
                    """INSERT INTO outreach_metrics (metric_name, metric_value, labels, recorded_at)
                       VALUES (%s, %s, %s, %s)""",
                    (metric_name, float(value), json.dumps({}), now)
                )
                persisted += 1

            # Persist rates
            for metric_name, value in snapshot.get('rates', {}).items():
                cursor.execute(
                    """INSERT INTO outreach_metrics (metric_name, metric_value, labels, recorded_at)
                       VALUES (%s, %s, %s, %s)""",
                    (metric_name, float(value), json.dumps({}), now)
                )
                persisted += 1

            # Persist queue depths
            for queue_name, depth in snapshot.get('queues', {}).items():
                cursor.execute(
                    """INSERT INTO outreach_metrics (metric_name, metric_value, labels, recorded_at)
                       VALUES (%s, %s, %s, %s)""",
                    (f"queue_depth_{queue_name}", float(depth),
                     json.dumps({'queue': queue_name}), now)
                )
                persisted += 1

            self.db_conn.commit()
            logger.info(f"Metrics: Persisted {persisted} metrics to PostgreSQL.")

        except Exception as e:
            logger.error(f"Metrics: Failed to persist to DB: {e}")
            try:
                self.db_conn.rollback()
            except Exception:
                pass

        return persisted

    # ── Cleanup ───────────────────────────────────────────────────────────

    def cleanup_old_metrics(self, days: int = 30) -> int:
        """
        Delete metrics older than specified days from PostgreSQL.
        
        Returns number of deleted rows.
        """
        if not self.db_conn:
            return 0

        try:
            cursor = self.db_conn.cursor()
            cursor.execute(
                "DELETE FROM outreach_metrics WHERE recorded_at < NOW() - INTERVAL '%s days'",
                (days,)
            )
            deleted = cursor.rowcount
            self.db_conn.commit()
            logger.info(f"Metrics: Cleaned up {deleted} old metric rows (>{days} days).")
            return deleted
        except Exception as e:
            logger.error(f"Metrics: Failed to cleanup old metrics: {e}")
            try:
                self.db_conn.rollback()
            except Exception:
                pass
            return 0
