"""
Constants used across the outreach engine.
"""

class AccountState:
    """Account health states."""
    HEALTHY = 'HEALTHY'
    DEGRADED = 'DEGRADED'
    COOLDOWN = 'COOLDOWN'
    RESTRICTED = 'RESTRICTED'
    QUARANTINED = 'QUARANTINED'
    DISABLED = 'DISABLED'
    
    ALL = [HEALTHY, DEGRADED, COOLDOWN, RESTRICTED, QUARANTINED, DISABLED]
    SEND_ALLOWED = [HEALTHY, DEGRADED]  # Only these states allow outreach

class RiskLevel:
    """Risk levels for accounts and operations."""
    LOW = 'LOW'
    MEDIUM = 'MEDIUM'
    HIGH = 'HIGH'
    CRITICAL = 'CRITICAL'
    ALL = [LOW, MEDIUM, HIGH, CRITICAL]

class Eligibility:
    """Eligibility states for leads."""
    ELIGIBLE = 'ELIGIBLE'
    RISKY = 'RISKY'
    COOLDOWN = 'COOLDOWN'
    BLOCKED = 'BLOCKED'
    CONTACTED = 'CONTACTED'
    FAILED = 'FAILED'
    ALL = [ELIGIBLE, RISKY, COOLDOWN, BLOCKED, CONTACTED, FAILED]

class DeliveryState:
    """States of message delivery."""
    PENDING = 'pending'
    CLAIMED = 'processing'  # matches existing DB values
    SENDING = 'sending'
    SENT = 'sent'
    FAILED = 'failed'
    SKIPPED = 'skipped'
    RETRY_WAIT = 'retry_wait'
    UNKNOWN = 'unknown'
    RECONCILIATION = 'reconciliation'
    ALL = [PENDING, CLAIMED, SENDING, SENT, FAILED, SKIPPED, RETRY_WAIT, UNKNOWN, RECONCILIATION]

class CampaignMode:
    """Operational modes for campaigns."""
    NORMAL = 'normal'
    CANARY = 'canary'
    DRY_RUN = 'dry_run'
    PAUSED = 'paused'
    STOPPED = 'stopped'
    ALL = [NORMAL, CANARY, DRY_RUN, PAUSED, STOPPED]
