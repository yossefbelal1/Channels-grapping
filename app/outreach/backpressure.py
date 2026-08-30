import logging
from typing import Dict

logger = logging.getLogger(__name__)

class BackpressureLevel:
    NORMAL = 'NORMAL'
    HIGH = 'HIGH'
    CRITICAL = 'CRITICAL'


class BackpressureManager:
    def __init__(self, redis_conn, 
                 outreach_high_threshold: int = 500,
                 outreach_critical_threshold: int = 2000,
                 validation_high_threshold: int = 1000,
                 validation_critical_threshold: int = 3000):
        self.redis_conn = redis_conn
        self.outreach_high = outreach_high_threshold
        self.outreach_critical = outreach_critical_threshold
        self.validation_high = validation_high_threshold
        self.validation_critical = validation_critical_threshold
        
    def _safe_llen(self, queue_name: str) -> int:
        try:
            return self.redis_conn.llen(queue_name) or 0
        except Exception as e:
            logger.error(f"Failed to get queue length for {queue_name}: {e}")
            return 0
            
    def _safe_setex(self, key: str, ttl: int, value: str) -> None:
        try:
            self.redis_conn.setex(key, ttl, value)
        except Exception as e:
            logger.error(f"Failed to write to redis for {key}: {e}")
    
    def get_outreach_level(self) -> str:
        """
        Check outreach queue pressure.
        Reads outreach:high + outreach:normal + outreach:low depths.
        Returns BackpressureLevel.
        Also writes result to Redis key backpressure:outreach:level (TTL 60s)
        for other workers to read.
        """
        total = (self._safe_llen('outreach:high') + 
                 self._safe_llen('outreach:normal') + 
                 self._safe_llen('outreach:low'))
                 
        level = BackpressureLevel.NORMAL
        if total >= self.outreach_critical:
            level = BackpressureLevel.CRITICAL
        elif total >= self.outreach_high:
            level = BackpressureLevel.HIGH
            
        self._safe_setex('backpressure:outreach:level', 60, level)
        return level
    
    def get_validation_level(self) -> str:
        """
        Check validation queue pressure.
        Reads queue:critical + queue:high + queue:normal + queue:low depths.
        Returns BackpressureLevel.
        Also writes to Redis key backpressure:validation:level (TTL 60s).
        """
        total = (self._safe_llen('queue:critical') + 
                 self._safe_llen('queue:high') + 
                 self._safe_llen('queue:normal') + 
                 self._safe_llen('queue:low'))
                 
        level = BackpressureLevel.NORMAL
        if total >= self.validation_critical:
            level = BackpressureLevel.CRITICAL
        elif total >= self.validation_high:
            level = BackpressureLevel.HIGH
            
        self._safe_setex('backpressure:validation:level', 60, level)
        return level
    
    def should_pause_discovery(self) -> bool:
        """Returns True if validation queue is at CRITICAL level."""
        return self.get_validation_level() == BackpressureLevel.CRITICAL
    
    def should_reduce_discovery(self) -> bool:
        """Returns True if validation queue is at HIGH level or above."""
        return self.get_validation_level() in (BackpressureLevel.HIGH, BackpressureLevel.CRITICAL)
    
    def should_pause_outreach_enqueue(self) -> bool:
        """Returns True if outreach queue is at CRITICAL level."""
        return self.get_outreach_level() == BackpressureLevel.CRITICAL
    
    def get_status(self) -> Dict[str, str]:
        """Return dict with both levels for dashboard."""
        return {
            'outreach_level': self.get_outreach_level(),
            'validation_level': self.get_validation_level()
        }
