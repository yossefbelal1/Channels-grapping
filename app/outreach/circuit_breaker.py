import logging
from typing import Tuple

logger = logging.getLogger(__name__)

class CircuitBreaker:
    """
    Automatic stop conditions based on Redis counters to block problematic executions.
    Fails closed (blocks) if Redis is unavailable.
    """

    def __init__(self, redis_conn):
        self.redis = redis_conn

    def check_account_circuit(self, session_name: str) -> Tuple[bool, str]:
        """Checks if the account circuit is open (blocked). Returns (is_open, reason)."""
        try:
            if self.redis.exists(f"circuit:account:{session_name}:flood_spike"):
                return True, "Flood wait spike detected"
            if self.redis.exists(f"circuit:account:{session_name}:error_spike"):
                return True, "Error spike detected"
            if self.redis.exists(f"circuit:account:{session_name}:connectivity"):
                return True, "Connectivity failure detected"
            return False, ""
        except Exception as e:
            logger.error(f"Redis error checking account circuit for {session_name}: {e}")
            return True, "Circuit breaker check failed (fail-closed)"

    def check_campaign_circuit(self, campaign_id: str) -> Tuple[bool, str]:
        """Checks if the campaign circuit is open (blocked). Returns (is_open, reason)."""
        try:
            if self.redis.exists(f"circuit:campaign:{campaign_id}:rejection_spike"):
                return True, "Rejection spike detected"
            return False, ""
        except Exception as e:
            logger.error(f"Redis error checking campaign circuit for {campaign_id}: {e}")
            return True, "Circuit breaker check failed (fail-closed)"

    def check_lead_circuit(self, lead_id: str) -> Tuple[bool, str]:
        """Checks if the lead circuit is open (blocked). Returns (is_open, reason)."""
        try:
            if self.redis.exists(f"circuit:lead:{lead_id}:retry_explosion"):
                return True, "Retry explosion detected"
            return False, ""
        except Exception as e:
            logger.error(f"Redis error checking lead circuit for {lead_id}: {e}")
            return True, "Circuit breaker check failed (fail-closed)"

    def record_flood_wait(self, session_name: str) -> None:
        """Records a flood wait and opens circuit if limit reached."""
        try:
            key = f"circuit:account:{session_name}:flood_count"
            count = self.redis.incr(key)
            if count == 1:
                self.redis.expire(key, 1800)
            if count >= 3:
                self.redis.setex(f"circuit:account:{session_name}:flood_spike", 3600, "1")
        except Exception as e:
            logger.warning(f"Redis error in record_flood_wait for {session_name}: {e}")

    def record_error(self, session_name: str) -> None:
        """Records an error and opens circuit if limit reached (5 in 30min)."""
        try:
            key = f"circuit:account:{session_name}:error_count"
            count = self.redis.incr(key)
            if count == 1:
                self.redis.expire(key, 1800)  # 30 min
            if count >= 5:
                self.redis.setex(f"circuit:account:{session_name}:error_spike", 3600, "1")
        except Exception as e:
            logger.warning(f"Redis error in record_error for {session_name}: {e}")

    def record_rejection(self, campaign_id: str) -> None:
        """Records a rejection and opens circuit if limit reached."""
        try:
            key = f"circuit:campaign:{campaign_id}:rejection_count"
            count = self.redis.incr(key)
            if count == 1:
                self.redis.expire(key, 3600)
            if count >= 10:
                self.redis.setex(f"circuit:campaign:{campaign_id}:rejection_spike", 7200, "1")
        except Exception as e:
            logger.warning(f"Redis error in record_rejection for {campaign_id}: {e}")

    def record_retry(self, lead_id: str) -> None:
        """Records a retry and opens circuit if limit reached."""
        try:
            key = f"circuit:lead:{lead_id}:retry_count"
            count = self.redis.incr(key)
            if count == 1:
                self.redis.expire(key, 86400)
            if count >= 5:
                self.redis.setex(f"circuit:lead:{lead_id}:retry_explosion", 86400, "1")
        except Exception as e:
            logger.warning(f"Redis error in record_retry for {lead_id}: {e}")

    def record_connectivity_failure(self, session_name: str) -> None:
        """Records a connectivity failure and temporarily opens circuit."""
        try:
            self.redis.setex(f"circuit:account:{session_name}:connectivity", 300, "1")
        except Exception as e:
            logger.warning(f"Redis error in record_connectivity_failure for {session_name}: {e}")

    def clear_account_circuit(self, session_name: str) -> None:
        """Clears all circuit breaker keys for an account."""
        try:
            self.redis.delete(
                f"circuit:account:{session_name}:flood_spike",
                f"circuit:account:{session_name}:error_spike",
                f"circuit:account:{session_name}:connectivity",
                f"circuit:account:{session_name}:flood_count",
                f"circuit:account:{session_name}:error_count"
            )
        except Exception as e:
            logger.warning(f"Redis error in clear_account_circuit for {session_name}: {e}")

    def clear_campaign_circuit(self, campaign_id: str) -> None:
        """Clears all circuit breaker keys for a campaign."""
        try:
            self.redis.delete(
                f"circuit:campaign:{campaign_id}:rejection_spike",
                f"circuit:campaign:{campaign_id}:rejection_count"
            )
        except Exception as e:
            logger.warning(f"Redis error in clear_campaign_circuit for {campaign_id}: {e}")
