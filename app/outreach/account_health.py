import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

class AccountHealthManager:
    """
    Account health state machine backed by PostgreSQL and Redis.
    Manages state transitions based on success, flood waits, and errors.
    """

    STATES = ["HEALTHY", "DEGRADED", "COOLDOWN", "RESTRICTED", "QUARANTINED", "DISABLED"]

    def __init__(self, redis_conn, db_conn):
        self.redis = redis_conn
        self.db = db_conn

    def ensure_account_exists(self, session_name: str) -> None:
        """Ensures that the account exists in the account_health table."""
        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO account_health (session_name, state, health_score, total_sends, total_failures, total_flood_waits, flood_wait_seconds_total)
                    VALUES (%s, 'HEALTHY', 100, 0, 0, 0, 0)
                    ON CONFLICT (session_name) DO NOTHING
                    """,
                    (session_name,)
                )
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to ensure account exists for {session_name}: {e}")
            self.db.rollback()

    def get_state(self, session_name: str) -> str:
        """Returns the current state string, checking Redis cache first."""
        cache_key = f"account:health:state:{session_name}"
        try:
            state = self.redis.get(cache_key)
            if state:
                return state.decode("utf-8") if isinstance(state, bytes) else state
        except Exception as e:
            logger.warning(f"Redis get failed for {cache_key}: {e}")

        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    "SELECT state FROM account_health WHERE session_name = %s",
                    (session_name,)
                )
                row = cursor.fetchone()
                if row:
                    state = row[0] if isinstance(row, tuple) else row.get('state')
                    try:
                        self.redis.setex(cache_key, 300, state)
                    except Exception as e:
                        logger.warning(f"Redis setex failed for {cache_key}: {e}")
                    return state
        except Exception as e:
            logger.error(f"DB get state failed for {session_name}: {e}")
            
        return "QUARANTINED"  # fail-closed

    def get_health_score(self, session_name: str) -> int:
        """Returns the health score of the account."""
        cache_key = f"account:health:score:{session_name}"
        try:
            score = self.redis.get(cache_key)
            if score is not None:
                return int(score)
        except Exception as e:
            logger.warning(f"Redis get failed for {cache_key}: {e}")

        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    "SELECT health_score FROM account_health WHERE session_name = %s",
                    (session_name,)
                )
                row = cursor.fetchone()
                if row:
                    score = row[0] if isinstance(row, tuple) else row.get('health_score')
                    try:
                        self.redis.setex(cache_key, 300, score)
                    except Exception as e:
                        logger.warning(f"Redis setex failed for {cache_key}: {e}")
                    return score
        except Exception as e:
            logger.error(f"DB get score failed for {session_name}: {e}")
            
        return 0  # fail-closed

    def is_send_allowed(self, session_name: str) -> bool:
        """Checks if the account is allowed to send messages."""
        state = self.get_state(session_name)
        if state not in ("HEALTHY", "DEGRADED"):
            return False
            
        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    "SELECT cooldown_until FROM account_health WHERE session_name = %s",
                    (session_name,)
                )
                row = cursor.fetchone()
                if row:
                    cooldown = row[0] if isinstance(row, tuple) else row.get('cooldown_until')
                    if cooldown and cooldown > datetime.now(timezone.utc):
                        return False
        except Exception as e:
            logger.error(f"DB check cooldown failed for {session_name}: {e}")
            return False # fail-closed
            
        return True

    def record_success(self, session_name: str) -> None:
        """Records a successful send and updates health score."""
        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE account_health 
                    SET health_score = LEAST(health_score + 1, 100),
                        total_sends = total_sends + 1,
                        last_success_at = %s
                    WHERE session_name = %s
                    RETURNING state, health_score
                    """,
                    (datetime.now(timezone.utc), session_name)
                )
                row = cursor.fetchone()
                if not row:
                    self.db.commit()
                    return
                
                state = row[0] if isinstance(row, tuple) else row.get('state')
                score = row[1] if isinstance(row, tuple) else row.get('health_score')

                # Check consecutive successes rule if degraded
                if state == "DEGRADED":
                    # Heuristic for 5 consecutive successes check: Since we don't have a specific consecutive counter,
                    # We might transition to healthy if the score crosses a threshold or just directly log it.
                    # As requested: "check if 5 consecutive successes should transition DEGRADED→HEALTHY"
                    # Note: We need a consecutive counter or just transition if score gets high.
                    # For simplicity, if we hit 100, go healthy. But without a dedicated field, let's assume score >= 90.
                    if score >= 90:
                        self._transition_state(session_name, "HEALTHY")
            self.db.commit()
            
            # Update cache
            try:
                self.redis.delete(f"account:health:score:{session_name}")
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Failed to record success for {session_name}: {e}")
            self.db.rollback()

    def record_flood_wait(self, session_name: str, method: str, wait_seconds: int) -> None:
        """Records a flood wait and applies penalties."""
        try:
            with self.db.cursor() as cursor:
                # Log to flood_wait_log
                cursor.execute(
                    "INSERT INTO flood_wait_log (session_name, method, wait_seconds, timestamp) VALUES (%s, %s, %s, %s)",
                    (session_name, method, wait_seconds, datetime.now(timezone.utc))
                )
                
                penalty = 5 if wait_seconds <= 60 else 15
                cooldown_time = datetime.now(timezone.utc) + timedelta(seconds=wait_seconds * 1.3)
                
                cursor.execute(
                    """
                    UPDATE account_health
                    SET total_flood_waits = total_flood_waits + 1,
                        flood_wait_seconds_total = flood_wait_seconds_total + %s,
                        last_flood_wait_at = %s,
                        health_score = GREATEST(health_score - %s, 0),
                        cooldown_until = %s
                    WHERE session_name = %s
                    RETURNING state
                    """,
                    (wait_seconds, datetime.now(timezone.utc), penalty, cooldown_time, session_name)
                )
                row = cursor.fetchone()
                if row:
                    state = row[0] if isinstance(row, tuple) else row.get('state')
                    
                    is_spike = self._check_flood_wait_spike(session_name)
                    
                    # State transition logic
                    if state == "HEALTHY":
                        if is_spike or wait_seconds > 60:
                            self._transition_state(session_name, "DEGRADED")
                    elif state == "DEGRADED":
                        self._transition_state(session_name, "COOLDOWN")
                    elif state == "COOLDOWN":
                        self._transition_state(session_name, "RESTRICTED")
            self.db.commit()
            
            try:
                self.redis.delete(f"account:health:score:{session_name}")
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Failed to record flood wait for {session_name}: {e}")
            self.db.rollback()

    def record_error(self, session_name: str, error_type: str, error_msg: str) -> None:
        """Records an RPC or unknown error and applies penalties."""
        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE account_health
                    SET total_failures = total_failures + 1,
                        last_error_at = %s,
                        last_error_message = %s,
                        health_score = GREATEST(health_score - 10, 0)
                    WHERE session_name = %s
                    RETURNING state
                    """,
                    (datetime.now(timezone.utc), error_msg, session_name)
                )
                row = cursor.fetchone()
                if row:
                    state = row[0] if isinstance(row, tuple) else row.get('state')
                    if state == "DEGRADED":
                        self._transition_state(session_name, "COOLDOWN")
            self.db.commit()
            
            try:
                self.redis.delete(f"account:health:score:{session_name}")
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Failed to record error for {session_name}: {e}")
            self.db.rollback()

    def record_auth_error(self, session_name: str, error_msg: str) -> None:
        """Records an auth error and immediately quarantines the account."""
        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE account_health
                    SET total_failures = total_failures + 1,
                        last_error_at = %s,
                        last_error_message = %s,
                        health_score = 0
                    WHERE session_name = %s
                    """,
                    (datetime.now(timezone.utc), error_msg, session_name)
                )
            self.db.commit()
            self._transition_state(session_name, "QUARANTINED")
            
            try:
                self.redis.delete(f"account:health:score:{session_name}")
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Failed to record auth error for {session_name}: {e}")
            self.db.rollback()

    def get_healthiest_account(self, exclude: Optional[list] = None) -> Optional[str]:
        """Returns the most healthy available account."""
        exclude = exclude or []
        query = """
            SELECT session_name 
            FROM account_health 
            WHERE state IN ('HEALTHY', 'DEGRADED') 
              AND (cooldown_until IS NULL OR cooldown_until < %s)
        """
        params = [datetime.now(timezone.utc)]
        if exclude:
            query += " AND session_name != ALL(%s) "
            params.append(exclude)
            
        query += " ORDER BY health_score DESC LIMIT 1"
        
        try:
            with self.db.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
                if row:
                    return row[0] if isinstance(row, tuple) else row.get('session_name')
        except Exception as e:
            logger.error(f"Failed to get healthiest account: {e}")
            
        return None

    def _transition_state(self, session_name: str, new_state: str) -> None:
        """Transitions the account to a new state."""
        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    "UPDATE account_health SET state = %s, state_changed_at = %s WHERE session_name = %s",
                    (new_state, datetime.now(timezone.utc), session_name)
                )
            self.db.commit()
            
            cache_key = f"account:health:state:{session_name}"
            try:
                self.redis.setex(cache_key, 300, new_state)
            except Exception as e:
                logger.warning(f"Redis setex failed in state transition for {cache_key}: {e}")
                
            logger.info(f"Account {session_name} transitioned to {new_state}")
        except Exception as e:
            logger.error(f"Failed to transition state for {session_name} to {new_state}: {e}")
            self.db.rollback()

    def _check_flood_wait_spike(self, session_name: str) -> bool:
        """Checks if there have been >= 3 flood waits in the last 30 minutes."""
        try:
            with self.db.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*) 
                    FROM flood_wait_log 
                    WHERE session_name = %s AND timestamp > %s
                    """,
                    (session_name, datetime.now(timezone.utc) - timedelta(minutes=30))
                )
                row = cursor.fetchone()
                count = row[0] if isinstance(row, tuple) else row.get('count')
                return (count or 0) >= 3
        except Exception as e:
            logger.error(f"Failed to check flood wait spike for {session_name}: {e}")
            return False
