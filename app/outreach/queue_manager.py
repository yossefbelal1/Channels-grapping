import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Queue names
QUEUE_HIGH = 'outreach:high'
QUEUE_NORMAL = 'outreach:normal'
QUEUE_LOW = 'outreach:low'


class OutreachQueueManager:
    def __init__(self, redis_conn):
        self.redis_conn = redis_conn
    
    def enqueue(self, lead_id: str, campaign_id: str, risk_level: str = 'LOW',
                delivery_id: str = None, account: str = None,
                attempt_count: int = 0) -> Optional[str]:
        """
        Add a lead to the appropriate outreach queue based on risk level.
        
        LOW → outreach:high (highest priority = fastest processing)
        MEDIUM → outreach:normal
        HIGH/CRITICAL → outreach:low (lowest priority, may require review)
        
        Returns job_id or None on failure.
        """
        job_id = str(uuid.uuid4())
        delivery_id = delivery_id or str(uuid.uuid4())
        payload = {
            'job_id': job_id,
            'delivery_id': delivery_id,
            'lead_id': lead_id,
            'campaign_id': campaign_id,
            'account': account,
            'attempt_count': attempt_count,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'risk_level': risk_level
        }
        
        if risk_level == 'LOW':
            queue = QUEUE_HIGH
        elif risk_level == 'MEDIUM':
            queue = QUEUE_NORMAL
        else:
            queue = QUEUE_LOW
            
        try:
            self.redis_conn.lpush(queue, json.dumps(payload))
            return job_id
        except Exception as e:
            logger.error(f"Failed to enqueue job: {e}")
            return None
    
    def dequeue(self) -> Optional[Dict[str, Any]]:
        """
        Pop highest-priority job from outreach queues.
        Checks outreach:high first, then outreach:normal, then outreach:low.
        Uses RPOP (FIFO within each priority).
        Returns parsed job dict or None.
        """
        try:
            for queue in [QUEUE_HIGH, QUEUE_NORMAL, QUEUE_LOW]:
                item = self.redis_conn.rpop(queue)
                if item:
                    return json.loads(item)
            return None
        except Exception as e:
            logger.error(f"Failed to dequeue job: {e}")
            return None
    
    def requeue(self, job: Dict[str, Any], delay_seconds: int = 0) -> bool:
        """
        Re-queue a failed job for retry. Increments attempt_count.
        If delay_seconds > 0, the job is placed in the low-priority queue.
        """
        job['attempt_count'] = job.get('attempt_count', 0) + 1
        
        queue = QUEUE_LOW if delay_seconds > 0 else QUEUE_NORMAL
        if delay_seconds == 0:
            risk_level = job.get('risk_level', 'LOW')
            if risk_level == 'LOW':
                queue = QUEUE_HIGH
            elif risk_level == 'MEDIUM':
                queue = QUEUE_NORMAL
            else:
                queue = QUEUE_LOW
                
        try:
            self.redis_conn.lpush(queue, json.dumps(job))
            return True
        except Exception as e:
            logger.error(f"Failed to requeue job: {e}")
            return False
    
    def get_depths(self) -> Dict[str, int]:
        """Return current depth of each outreach queue."""
        depths = {QUEUE_HIGH: 0, QUEUE_NORMAL: 0, QUEUE_LOW: 0}
        try:
            depths[QUEUE_HIGH] = self.redis_conn.llen(QUEUE_HIGH)
            depths[QUEUE_NORMAL] = self.redis_conn.llen(QUEUE_NORMAL)
            depths[QUEUE_LOW] = self.redis_conn.llen(QUEUE_LOW)
        except Exception as e:
            logger.error(f"Failed to get queue depths: {e}")
        return depths
    
    def get_total_pending(self) -> int:
        """Return total pending items across all outreach queues."""
        return sum(self.get_depths().values())
