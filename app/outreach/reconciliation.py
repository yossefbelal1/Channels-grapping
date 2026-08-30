import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List

logger = logging.getLogger(__name__)

DEFAULT_STALE_CLAIM_MINUTES = 10
DEFAULT_MAX_RETRIES = 3


class ReconciliationManager:
    def __init__(self, redis_conn, db_conn, 
                 stale_claim_minutes: int = DEFAULT_STALE_CLAIM_MINUTES,
                 max_retries: int = DEFAULT_MAX_RETRIES):
        self.redis_conn = redis_conn
        self.db_conn = db_conn
        self.stale_claim_minutes = stale_claim_minutes
        self.max_retries = max_retries
    
    def find_stale_claims(self) -> List[Dict]:
        """
        Find campaign_logs rows that are stuck in 'processing' state
        for longer than stale_claim_minutes.
        
        Query:
        SELECT id, campaign_id, lead_id, delivery_id, attempt_count, last_attempt_at
        FROM campaign_logs
        WHERE status = 'processing'
          AND last_attempt_at < NOW() - INTERVAL '{stale_claim_minutes} minutes'
        """
        try:
            with self.db_conn.cursor() as cur:
                query = """
                    SELECT id, campaign_id, lead_id, delivery_id, attempt_count, last_attempt_at
                    FROM campaign_logs
                    WHERE status = 'processing'
                      AND last_attempt_at < NOW() - CAST(%s AS INTERVAL)
                """
                interval_str = f"{self.stale_claim_minutes} minutes"
                cur.execute(query, (interval_str,))
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to find stale claims: {e}")
            return []
    
    def reconcile(self, stale_claim: Dict) -> str:
        """
        Reconcile a single stale claim.
        
        1. Check Redis idempotency token campaign:delivered:{campaign_id}:{lead_id}
           - If exists → message was delivered → mark SENT
        2. If no token and attempt_count < max_retries
           → reset to PENDING (increment attempt_count)
        3. If no token and attempt_count >= max_retries
           → mark FAILED with 'Exceeded max retries after unknown delivery state'
        
        Returns action taken: 'marked_sent', 'reset_pending', 'marked_failed'
        """
        campaign_id = stale_claim.get('campaign_id')
        lead_id = stale_claim.get('lead_id')
        attempt_count = stale_claim.get('attempt_count', 0)
        log_id = stale_claim.get('id')
        
        token_key = f"campaign:delivered:{campaign_id}:{lead_id}"
        
        try:
            token_exists = self.redis_conn.exists(token_key)
        except Exception as e:
            logger.error(f"Redis error checking token {token_key}: {e}")
            return 'error'
            
        try:
            with self.db_conn.cursor() as cur:
                if token_exists:
                    cur.execute(
                        "UPDATE campaign_logs SET status = 'SENT' WHERE id = %s",
                        (log_id,)
                    )
                    self.db_conn.commit()
                    return 'marked_sent'
                
                if attempt_count < self.max_retries:
                    cur.execute(
                        "UPDATE campaign_logs SET status = 'PENDING', attempt_count = attempt_count + 1 WHERE id = %s",
                        (log_id,)
                    )
                    self.db_conn.commit()
                    return 'reset_pending'
                else:
                    cur.execute(
                        "UPDATE campaign_logs SET status = 'FAILED', error_message = 'Exceeded max retries after unknown delivery state' WHERE id = %s",
                        (log_id,)
                    )
                    self.db_conn.commit()
                    return 'marked_failed'
        except Exception as e:
            logger.error(f"DB error reconciling claim {log_id}: {e}")
            self.db_conn.rollback()
            return 'error'
    
    def run_reconciliation_cycle(self) -> Dict[str, int]:
        """
        Run a full reconciliation cycle.
        Returns dict with counts: {marked_sent: N, reset_pending: N, marked_failed: N}
        """
        counts = {'marked_sent': 0, 'reset_pending': 0, 'marked_failed': 0}
        
        claims = self.find_stale_claims()
        for claim in claims:
            result = self.reconcile(claim)
            if result in counts:
                counts[result] += 1
                
        return counts
