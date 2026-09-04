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


class OutreachPriority:
    """Outreach Priority Tiers inferred from commercial fit and service need."""
    P0 = 'P0'  # High-confidence commercial/business channel + strong service fit + contactable
    P1 = 'P1'  # Strong commercial channel with clear monetization footprint
    P2 = 'P2'  # Relevant Forex business channel with moderate commercial signals
    P3 = 'P3'  # Relevant Forex channel, but generic/educational/community (low commercial signals)
    P4 = 'P4'  # Minimal commercial fit / non-business channel

    ALL = [P0, P1, P2, P3, P4]
    ORDER = {'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3, 'P4': 4}


class ServiceNeedType:
    """Inferred service fit types from channel operations and content."""
    CHANNEL_MANAGEMENT = 'channel_management'           # Operation, daily publishing & admin load
    ADVERTISING_MANAGEMENT = 'advertising_management'   # VIP monetization, ad placements & sponsorships
    GROWTH_MARKETING = 'growth_marketing'               # Audience growth, promo campaigns
    VERIFICATION = 'verification'                       # Brand verification / official badge
    ACCOUNT_MANAGEMENT = 'account_management'           # Copy trading, portfolio management services
    PARTNERSHIPS = 'partnerships'                       # Broker affiliate, prop firm & IB deals
    CONTENT_MEDIA = 'content_media'                     # Charting, technical analysis, daily recaps
    NONE = 'none'

    ALL = [
        CHANNEL_MANAGEMENT, ADVERTISING_MANAGEMENT, GROWTH_MARKETING,
        VERIFICATION, ACCOUNT_MANAGEMENT, PARTNERSHIPS, CONTENT_MEDIA, NONE
    ]

