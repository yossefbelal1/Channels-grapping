"""
Dry-run mode controller.
"""

import os
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

def is_dry_run() -> bool:
    """
    Check if the outreach engine is in dry-run mode via environment variable.
    
    Returns:
        bool: True if in dry-run mode, False otherwise.
    """
    return os.environ.get("OUTREACH_DRY_RUN", "false").lower() == "true"

def log_dry_run_decision(
    lead_id: str,
    campaign_id: str,
    contact_username: str,
    account: str,
    risk_level: str,
    eligibility: str,
    message_preview: str
) -> Dict[str, Any]:
    """
    Log what would have been sent if not in dry-run mode.
    
    Args:
        lead_id: ID of the lead
        campaign_id: ID of the campaign
        contact_username: Username of the target contact
        account: Account session name to be used
        risk_level: Calculated risk level
        eligibility: Calculated eligibility status
        message_preview: Preview of the message to send
        
    Returns:
        dict: Metadata describing the decision.
    """
    decision = {
        "action": "dry_run_skip",
        "lead_id": lead_id,
        "campaign_id": campaign_id,
        "contact_username": contact_username,
        "account": account,
        "risk_level": risk_level,
        "eligibility": eligibility,
        "message_preview": message_preview
    }
    
    logger.info(
        "DRY RUN DECISION: Would have sent message from %s to %s (lead: %s, campaign: %s). "
        "Risk: %s, Eligibility: %s. Preview: %s",
        account,
        contact_username,
        lead_id,
        campaign_id,
        risk_level,
        eligibility,
        message_preview[:50] + "..." if len(message_preview) > 50 else message_preview
    )
    
    return decision
