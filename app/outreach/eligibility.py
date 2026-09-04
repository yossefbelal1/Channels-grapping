import logging
from datetime import datetime, timezone
from typing import Tuple

logger = logging.getLogger(__name__)

SYSTEM_KEYWORDS = {
    'addlist', 'everyone', 'share', 'joinchat', 'setlanguage', 'proxy', 'socks',
    'c', 's', 'm', 'i', '4030', 'http', 'https', 't', 'me', 'join', 'channel',
    'group', 'admin', 'contact', 'support', 'null', 'none', 'undefined'
}

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
        # 2. Not in blacklist (entity_username_or_link column in blacklist table)
        cu_clean = contact_username.lstrip('@')
        db_cursor.execute("""
            SELECT 1 FROM blacklist 
            WHERE entity_username_or_link = %s 
               OR entity_username_or_link = %s
               OR entity_username_or_link = %s
        """, (contact_username, cu_clean, f"@{cu_clean}"))
        if db_cursor.fetchone():
            return "BLOCKED", "Contact is blacklisted"
            
        # 3. Lead status is not 'rejected' and not marked inactive
        db_cursor.execute("SELECT status, next_eligible_at, risk_score, description FROM leads WHERE id = %s", (lead_id,))
        lead_row = db_cursor.fetchone()
        status = None
        next_eligible = None
        lead_risk_score = None
        lead_desc = None
        if lead_row:
            if isinstance(lead_row, dict):
                status = lead_row.get('status')
                next_eligible = lead_row.get('next_eligible_at')
                lead_risk_score = lead_row.get('risk_score')
                lead_desc = lead_row.get('description')
            elif isinstance(lead_row, (list, tuple)):
                status = lead_row[0] if len(lead_row) > 0 else None
                next_eligible = lead_row[1] if len(lead_row) > 1 else None
                lead_risk_score = lead_row[2] if len(lead_row) > 2 else None
                lead_desc = lead_row[3] if len(lead_row) > 3 else None

        if status == 'rejected':
            return "BLOCKED", "Lead is rejected"
            
        if lead_desc and str(lead_desc).strip().lower().startswith('inactive channel'):
            return "BLOCKED", "Channel marked inactive"
                
        # 4. Not already contacted in this campaign
        db_cursor.execute("""
            SELECT 1 FROM campaign_logs 
            WHERE lead_id = %s AND campaign_id = %s AND status = 'sent'
        """, (lead_id, campaign_id))
        if db_cursor.fetchone():
            return "CONTACTED", "Already contacted in this campaign"
            
        # 5. Contact username not already messaged via another lead
        db_cursor.execute("""
            SELECT 1 FROM campaign_logs cl
            JOIN leads l ON cl.lead_id = l.id
            WHERE (l.contact_username = %s OR l.contact_username = %s) AND cl.status = 'sent'
        """, (contact_username, cu_clean))
        if db_cursor.fetchone():
            return "CONTACTED", "Username already messaged via another lead"
            
        # 6. Per-lead cooldown check
        if next_eligible:
            if next_eligible.tzinfo is None:
                next_eligible = next_eligible.replace(tzinfo=timezone.utc)
            if next_eligible > datetime.now(timezone.utc):
                return "COOLDOWN", "Lead is in cooldown"
                
        # 7. No permanent failure history for this contact (3+ failures)
        db_cursor.execute("""
            SELECT COUNT(*) FROM campaign_logs cl
            JOIN leads l ON cl.lead_id = l.id
            WHERE (l.contact_username = %s OR l.contact_username = %s) AND cl.status = 'failed'
        """, (contact_username, cu_clean))
        fail_row = db_cursor.fetchone()
        fail_count = 0
        if fail_row:
            if isinstance(fail_row, dict):
                fail_count = fail_row.get('count', 0)
            elif isinstance(fail_row, (list, tuple)):
                fail_count = fail_row[0] if len(fail_row) > 0 else 0
        if fail_count >= 3:
            return "FAILED", "Permanent failure history threshold reached"
            
        # 8. Risk score check
        if lead_risk_score and int(lead_risk_score) > 75:
            return "RISKY", f"Risk score is {lead_risk_score}"
            
    except Exception as e:
        logger.error(f"DB error checking eligibility: {e}")
        return "BLOCKED", "Database error"
        
    return "ELIGIBLE", "Eligible for outreach"
