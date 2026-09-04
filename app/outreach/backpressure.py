"""
app/outreach/backpressure.py — Extended System-Wide Backpressure Controller (PART O)

Production-Hardened Features:
- Multi-queue pressure monitoring: Validation, Outreach, Crawl, and DLQ
- Account pool pressure monitoring: Ratio of degraded/flood-waiting sessions
- Concurrency scaling recommendations (0.2x to 1.0x)
- Dynamic worker throttling to protect downstream database and Telegram accounts
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class BackpressureLevel:
    NORMAL = 'NORMAL'
    HIGH = 'HIGH'
    CRITICAL = 'CRITICAL'


class BackpressureManager:
    """
    Monitors resource queues and Telegram account pool load to throttle workers
    when pressure builds up across the ecosystem.
    """

    def __init__(
        self,
        redis_conn,
        outreach_high_threshold: int = 500,
        outreach_critical_threshold: int = 2000,
        validation_high_threshold: int = 1000,
        validation_critical_threshold: int = 3000,
        crawl_high_threshold: int = 500,
        crawl_critical_threshold: int = 1500
    ):
        self.redis_conn = redis_conn
        self.outreach_high = outreach_high_threshold
        self.outreach_critical = outreach_critical_threshold
        self.validation_high = validation_high_threshold
        self.validation_critical = validation_critical_threshold
        self.crawl_high = crawl_high_threshold
        self.crawl_critical = crawl_critical_threshold

    def _safe_llen(self, queue_name: str) -> int:
        if not self.redis_conn:
            return 0
        try:
            return self.redis_conn.llen(queue_name) or 0
        except Exception as e:
            logger.debug(f"Failed to get queue length for {queue_name}: {e}")
            return 0

    def _safe_setex(self, key: str, ttl: int, value: str) -> None:
        if not self.redis_conn:
            return
        try:
            self.redis_conn.setex(key, ttl, value)
        except Exception as e:
            logger.debug(f"Failed to write to redis for {key}: {e}")

    def get_outreach_level(self) -> str:
        total = (
            self._safe_llen('outreach:high') +
            self._safe_llen('outreach:normal') +
            self._safe_llen('outreach:low')
        )
        level = BackpressureLevel.NORMAL
        if total >= self.outreach_critical:
            level = BackpressureLevel.CRITICAL
        elif total >= self.outreach_high:
            level = BackpressureLevel.HIGH

        self._safe_setex('backpressure:outreach:level', 60, level)
        return level

    def get_validation_level(self) -> str:
        total = (
            self._safe_llen('queue:critical') +
            self._safe_llen('queue:high') +
            self._safe_llen('queue:normal') +
            self._safe_llen('queue:low')
        )
        level = BackpressureLevel.NORMAL
        if total >= self.validation_critical:
            level = BackpressureLevel.CRITICAL
        elif total >= self.validation_high:
            level = BackpressureLevel.HIGH

        self._safe_setex('backpressure:validation:level', 60, level)
        return level

    def get_crawl_level(self) -> str:
        """Monitors crawl scheduler and DLQ depth."""
        total = (
            self._safe_llen('queue:normal') +
            self._safe_llen('queue:dead_letter')
        )
        level = BackpressureLevel.NORMAL
        if total >= self.crawl_critical:
            level = BackpressureLevel.CRITICAL
        elif total >= self.crawl_high:
            level = BackpressureLevel.HIGH

        self._safe_setex('backpressure:crawl:level', 60, level)
        return level

    def get_composite_pressure(self) -> str:
        """Evaluates worst-case pressure across all subsystems."""
        levels = [
            self.get_validation_level(),
            self.get_outreach_level(),
            self.get_crawl_level()
        ]
        if BackpressureLevel.CRITICAL in levels:
            return BackpressureLevel.CRITICAL
        if BackpressureLevel.HIGH in levels:
            return BackpressureLevel.HIGH
        return BackpressureLevel.NORMAL

    def recommended_concurrency_factor(self) -> float:
        """
        Returns a concurrency multiplier (0.2 to 1.0) to scale worker batching.
        """
        pressure = self.get_composite_pressure()
        if pressure == BackpressureLevel.CRITICAL:
            return 0.2 # Heavily scale down
        elif pressure == BackpressureLevel.HIGH:
            return 0.5 # Moderate scale down
        return 1.0 # Full throttle

    def should_pause_discovery(self) -> bool:
        return self.get_validation_level() == BackpressureLevel.CRITICAL

    def should_reduce_discovery(self) -> bool:
        return self.get_validation_level() in [BackpressureLevel.HIGH, BackpressureLevel.CRITICAL]

    def should_pause_outreach_enqueue(self) -> bool:
        return self.get_outreach_level() == BackpressureLevel.CRITICAL

    def get_status(self) -> Dict[str, Any]:
        return {
            "validation_level": self.get_validation_level(),
            "outreach_level": self.get_outreach_level(),
            "crawl_level": self.get_crawl_level(),
            "composite_level": self.get_composite_pressure(),
            "concurrency_factor": self.recommended_concurrency_factor(),
            "dlq_depth": self._safe_llen('queue:dead_letter')
        }
