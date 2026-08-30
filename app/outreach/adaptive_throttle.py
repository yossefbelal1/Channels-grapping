import logging

logger = logging.getLogger(__name__)

class AdaptiveThrottle:
    """
    Adaptive throughput controller based on recent telemetry.
    """

    def __init__(self, redis_conn, session_name: str, min_delay: int = 60, max_delay: int = 600, default_delay: int = 120):
        self.redis = redis_conn
        self.session_name = session_name
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.default_delay = default_delay

    def get_next_delay(self) -> float:
        """Computes the adaptive delay based on recent telemetry."""
        try:
            successes_raw = self.redis.get(f"adaptive:{self.session_name}:successes")
            failures_raw = self.redis.get(f"adaptive:{self.session_name}:failures")
            flood_waits_raw = self.redis.get(f"adaptive:{self.session_name}:flood_waits")
            ewma_raw = self.redis.get(f"adaptive:{self.session_name}:ewma_delay")

            successes = int(successes_raw) if successes_raw else 0
            failures = int(failures_raw) if failures_raw else 0
            flood_waits = int(flood_waits_raw) if flood_waits_raw else 0
            ewma = float(ewma_raw) if ewma_raw else float(self.default_delay)

            success_rate = successes / max(successes + failures, 1)

            if flood_waits > 0:
                new_delay = max(ewma * 2.0, 300.0)
            elif success_rate >= 0.95 and flood_waits == 0:
                new_delay = ewma * 0.9
            elif success_rate >= 0.8:
                new_delay = ewma * 0.95
            elif success_rate >= 0.5:
                new_delay = ewma * 1.1
            else:
                new_delay = ewma * 1.5

            new_delay = max(self.min_delay, min(new_delay, self.max_delay))
            
            self.redis.setex(f"adaptive:{self.session_name}:ewma_delay", 3600, str(new_delay))
            return float(new_delay)
        except Exception as e:
            logger.error(f"Redis error in get_next_delay for {self.session_name}: {e}")
            return float(self.default_delay)

    def record_success(self) -> None:
        """Records a successful action."""
        key = f"adaptive:{self.session_name}:successes"
        try:
            self.redis.incr(key)
            self.redis.expire(key, 3600)
        except Exception as e:
            logger.warning(f"Redis error in record_success for {self.session_name}: {e}")

    def record_failure(self) -> None:
        """Records a failed action."""
        key = f"adaptive:{self.session_name}:failures"
        try:
            self.redis.incr(key)
            self.redis.expire(key, 3600)
        except Exception as e:
            logger.warning(f"Redis error in record_failure for {self.session_name}: {e}")

    def record_flood_wait(self, wait_seconds: int) -> None:
        """Records a flood wait."""
        key = f"adaptive:{self.session_name}:flood_waits"
        try:
            self.redis.incr(key)
            self.redis.expire(key, 3600)
        except Exception as e:
            logger.warning(f"Redis error in record_flood_wait for {self.session_name}: {e}")

    def reset(self) -> None:
        """Resets the adaptive throttle."""
        try:
            self.redis.delete(f"adaptive:{self.session_name}:successes")
            self.redis.delete(f"adaptive:{self.session_name}:failures")
            self.redis.delete(f"adaptive:{self.session_name}:flood_waits")
            self.redis.set(f"adaptive:{self.session_name}:ewma_delay", str(self.default_delay))
        except Exception as e:
            logger.warning(f"Redis error in reset for {self.session_name}: {e}")
