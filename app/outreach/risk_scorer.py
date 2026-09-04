import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

def classify_risk_level(score: int) -> str:
    """Classify the risk score into a risk level."""
    if score <= 25:
        return "LOW"
    elif score <= 50:
        return "MEDIUM"
    elif score <= 75:
        return "HIGH"
    else:
        return "CRITICAL"

def get_risk_behavior(risk_level: str) -> dict:
    """Return behavior dict for a given risk level."""
    behaviors = {
        "LOW": {"queue_priority": 1, "pacing_multiplier": 1.0, "requires_review": False},
        "MEDIUM": {"queue_priority": 2, "pacing_multiplier": 1.5, "requires_review": False},
        "HIGH": {"queue_priority": 3, "pacing_multiplier": 2.5, "requires_review": True},
        "CRITICAL": {"queue_priority": 4, "pacing_multiplier": 5.0, "requires_review": True},
    }
    return behaviors.get(risk_level, behaviors["CRITICAL"])

def calculate_risk_score(
    redis_conn,
    db_cursor,
    lead_id: str,
    session_name: str,
    campaign_id: str
) -> Tuple[int, str]:
    """
    Calculate outreach risk score for a lead from a specific account.
    
    Factors:
    1. Account health
    2. Recent FloodWait events
    3. Account failure rate
    4. Lead quality inverse
    5. Previous failures to this lead's contact
    
    Returns:
        Tuple of (risk_score 0-100, risk_level LOW/MEDIUM/HIGH/CRITICAL)
    """
    risk = 0
    
    # 1. Account health
    health = None
    try:
        redis_score = redis_conn.get(f"health:{session_name}:score")
        if redis_score is not None:
            health = float(redis_score)
    except Exception as e:
        logger.error(f"Redis error getting health: {e}")
        risk += 10
        
    if health is None:
        try:
            db_cursor.execute("SELECT health_score FROM account_health WHERE session_name = %s", (session_name,))
            row = db_cursor.fetchone()
            if row:
                val = row['health_score'] if isinstance(row, dict) else row[0]
                if val is not None:
                    health = float(val)
        except Exception as e:
            logger.error(f"DB error getting health: {e}")
            
    if health is not None:
        if health < 50:
            risk += 30
        elif health < 70:
            risk += 15
            
    # 2. Recent FloodWait events (timestamp column in flood_wait_log)
    try:
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        db_cursor.execute("""
            SELECT COUNT(*) FROM flood_wait_log 
            WHERE session_name = %s AND "timestamp" >= %s
        """, (session_name, one_hour_ago))
        row = db_cursor.fetchone()
        fw_count = (row[0] if isinstance(row, (list, tuple)) else (row.get('count', 0) if isinstance(row, dict) else 0)) if row else 0
        if fw_count >= 3:
            risk += 30
        elif fw_count >= 1:
            risk += 15
    except Exception as e:
        logger.error(f"DB error getting flood waits: {e}")
        
    # 3. Account failure rate
    try:
        db_cursor.execute("""
            SELECT total_failures, total_sends 
            FROM account_health 
            WHERE session_name = %s
        """, (session_name,))
        row = db_cursor.fetchone()
        if row:
            t_failures = row['total_failures'] if isinstance(row, dict) else row[0]
            t_sends = row['total_sends'] if isinstance(row, dict) else row[1]
            if t_sends and t_sends > 0:
                rate = float(t_failures or 0) / float(t_sends)
                if rate >= 0.3:
                    risk += 25
                elif rate >= 0.1:
                    risk += 10
    except Exception as e:
        logger.error(f"DB error getting failure rate: {e}")
        
    # 4. Lead quality inverse
    try:
        db_cursor.execute("SELECT lead_score FROM leads WHERE id = %s", (lead_id,))
        row = db_cursor.fetchone()
        if row:
            l_val = row['lead_score'] if isinstance(row, dict) else row[0]
            if l_val is not None:
                l_score = float(l_val)
                if l_score < 25:
                    risk += 20
                elif l_score < 50:
                    risk += 10
                elif l_score < 75:
                    risk += 5
    except Exception as e:
        logger.error(f"DB error getting lead score: {e}")
        
    # 5. Previous failures to this lead's contact
    try:
        db_cursor.execute("""
            SELECT COUNT(*) 
            FROM campaign_logs 
            WHERE lead_id = %s AND status = 'failed'
        """, (lead_id,))
        row = db_cursor.fetchone()
        fail_count = (row[0] if isinstance(row, (list, tuple)) else (row.get('count', 0) if isinstance(row, dict) else 0)) if row else 0
        if fail_count >= 3:
            risk += 20
        elif fail_count >= 1:
            risk += 10
    except Exception as e:
        logger.error(f"DB error getting previous failures: {e}")
        
    risk = min(100, max(0, risk))
    risk_level = classify_risk_level(risk)
    
    return risk, risk_level
