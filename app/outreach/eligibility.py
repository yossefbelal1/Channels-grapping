import logging
from datetime import datetime, timezone
from typing import Tuple

logger = logging.getLogger(__name__)

SYSTEM_KEYWORDS = {'addlist', 'everyone', 'share', 'joinchat', 'setlanguage', 'proxy', 'socks', 'c', 's', 'm', 'i', '4030'}

def check_eligibility(
    redis_conn,
    db_cursor,
    lead_id: str,
    campaign_id: str,
    contact_username: str
) -> Tuple[str, str]:
    """
    Determine if a lead is eligible for outreach.
    
    Checks (in order, short-circuit on first failure):
    1. Has valid contact_username
    2. Not in blacklist
    3. Lead status is not 'rejected'
    4. Not already contacted in this campaign
    5. Contact username not already messaged via another lead
    6. Per-lead cooldown check
    7. No permanent failure history for this contact
    8. Risk score check
    
    Returns:
        Tuple of (eligibility_status, reason_string)
    """
    # 1. Has valid contact_username
    if not contact_username:
        return "BLOCKED", "Empty contact username"
        
    cu_lower = contact_username.lower()
    if cu_lower in SYSTEM_KEYWORDS:
        return "BLOCKED", "System keyword in username"
        
    if cu_lower.endswith('bot') or cu_lower.endswith('_bot'):
        return "BLOCKED", "Bot username detected"
        
    # Redis fail-closed check
    try:
        redis_conn.ping()
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        return "BLOCKED", "Redis failure"
        
    try:
        # 2. Not in blacklist
        db_cursor.execute("SELECT 1 FROM blacklist WHERE username = %s OR lead_id = %s", (contact_username, lead_id))
        if db_cursor.fetchone():
            return "BLOCKED", "Contact is blacklisted"
            
        # 3. Lead status is not 'rejected'
        db_cursor.execute("SELECT status, next_eligible_at, risk_level FROM leads WHERE id = %s", (lead_id,))
        lead_row = db_cursor.fetchone()
        if lead_row:
            if lead_row.get('status') == 'rejected':
                return "BLOCKED", "Lead is rejected"
                
        # 4. Not already contacted in this campaign
        db_cursor.execute("""
            SELECT 1 FROM campaign_logs 
            WHERE lead_id = %s AND campaign_id = %s AND status = 'sent'
        """, (lead_id, campaign_id))
        if db_cursor.fetchone():
            return "CONTACTED", "Already contacted in this campaign"
            
        # 5. Contact username not already messaged via another lead
        db_cursor.execute("""
            SELECT 1 FROM campaign_logs 
            WHERE contact_username = %s AND status = 'sent'
        """, (contact_username,))
        if db_cursor.fetchone():
            return "CONTACTED", "Username already messaged via another lead"
            
        # 6. Per-lead cooldown check
        if lead_row and lead_row.get('next_eligible_at'):
            next_eligible = lead_row['next_eligible_at']
            if next_eligible.tzinfo is None:
                next_eligible = next_eligible.replace(tzinfo=timezone.utc)
            if next_eligible > datetime.now(timezone.utc):
                return "COOLDOWN", "Lead is in cooldown"
                
        # 7. No permanent failure history for this contact (3+ permanent failures)
        db_cursor.execute("""
            SELECT COUNT(*) as fail_count FROM campaign_logs 
            WHERE contact_username = %s AND status = 'failed' AND is_permanent = TRUE
        """, (contact_username,))
        fail_row = db_cursor.fetchone()
        if fail_row and fail_row.get('fail_count', 0) >= 3:
            return "FAILED", "Permanent failure history threshold reached"
            
        # 8. Risk score check
        if lead_row and lead_row.get('risk_level') in ('HIGH', 'CRITICAL'):
            return "RISKY", f"Risk level is {lead_row.get('risk_level')}"
            
    except Exception as e:
        logger.error(f"DB error checking eligibility: {e}")
        return "BLOCKED", "Database error"
        
    return "ELIGIBLE", "Eligible for outreach"
