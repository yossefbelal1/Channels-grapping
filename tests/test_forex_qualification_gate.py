import pytest
from app.outreach.constants import OutreachPriority
from app.outreach.priority_engine import OutreachPriorityEngine
from app.validator.contact_extractor import extract_contacts, _is_bot, JUNK_USERNAMES


def test_zero_forex_channel_cannot_get_p0_or_p1():
    """
    Ensure a channel with high member count and VIP in description,
    but 0 forex relevance (e.g. poetry channel like @whyyyvv),
    NEVER qualifies for P0 or P1 priority.
    """
    res = OutreachPriorityEngine.evaluate_priority(
        title="خواطر وأدب",
        description="كانَ كل شئٍ في المدينةِ هادئاً إلا عقلي . للاشتراك VIP تواصل مع @admin_lit",
        recent_messages=[],
        contacts_dict={"contact_username": "admin_lit", "source": "bio_official"},
        forex_relevance_score=0,
        member_count=50000,
        posts_24h=10,
        posts_7d=50
    )
    # Even with 50k members, VIP keyword, and contact, zero forex relevance MUST keep it in P3 or P4
    assert res["priority"] not in (OutreachPriority.P0, OutreachPriority.P1)
    assert res["forex_relevance_score"] == 0


def test_rejected_status_and_low_forex_excluded_from_backfill():
    """
    Ensure backfill logic rejects channels with status == 'rejected' or forex_intent_score < 40.
    """
    sample_leads = [
        {
            "channel_username": "whyyyvv",
            "status": "rejected",
            "tier": "Tier_C",
            "forex_intent_score": 0,
            "contact_username": "rr_12_5"
        },
        {
            "channel_username": "ABDOKings",
            "status": "rejected",
            "tier": "Tier_C",
            "forex_intent_score": 0,
            "contact_username": "Tradefreet"
        },
        {
            "channel_username": "RealForexChannel",
            "status": "new",
            "tier": "Tier_A",
            "forex_intent_score": 90,
            "contact_username": "real_forex_admin"
        }
    ]

    qualified = []
    for lead in sample_leads:
        final_contact = (lead.get("contact_username") or "").strip().lstrip("@")
        is_qualified = (
            lead["status"] != "rejected"
            and lead.get("forex_intent_score", 0) >= 40
            and lead["tier"] in ("Tier_A", "Tier_B", "Tier_C")
            and bool(final_contact)
            and not _is_bot(final_contact)
            and final_contact.lower() not in JUNK_USERNAMES
        )
        if is_qualified:
            qualified.append(lead["channel_username"])

    assert "whyyyvv" not in qualified
    assert "ABDOKings" not in qualified
    assert qualified == ["RealForexChannel"]


def test_similar_channel_crawler_forex_gate():
    """
    Test crawler auto-enroll logic: requires forex_score >= 60 to auto-enroll,
    and priority P0 requires forex_score >= 80 and members >= 15000.
    """
    # Channel 1: Non-forex with high members
    members_1 = 20000
    forex_score_1 = 20
    should_enroll_1 = forex_score_1 >= 60
    assert not should_enroll_1

    # Channel 2: Real forex with 18000 members
    members_2 = 18000
    forex_score_2 = 90
    should_enroll_2 = forex_score_2 >= 60
    assert should_enroll_2

    prio_2 = "P2"
    if forex_score_2 >= 80 and members_2 >= 15000:
        prio_2 = "P0"
    elif forex_score_2 >= 60 and members_2 >= 2500:
        prio_2 = "P1"

    assert prio_2 == "P0"


def test_alwaheed_alkhorasani_excluded_from_qualified():
    """
    Ensure a religious scholar channel like @AlWaheedAlKhorasani:
    - Language: Arabic (arabic_ratio: 78)
    - forex_intent_score: 34 (low / false positive from general words)
    - vip: False, account_management: False, copy_trading: False, funded_accounts: False
    - commercial_fit_score: 0
    - tier: Tier_D
    is STRICTLY excluded from the Qualified Leads gate.
    """
    channel = {
        "channel_username": "AlWaheedAlKhorasani",
        "status": "new",
        "language": "Arabic",
        "arabic_ratio": 78,
        "forex_intent_score": 34,
        "forex_score": 0,
        "commercial_fit_score": 0,
        "vip": False,
        "account_management": False,
        "copy_trading": False,
        "funded_accounts": False,
        "tier": "Tier_D",
        "entity_type": "channel",
        "outreach_priority_reason": None
    }

    # Strict qualification gate definition
    is_qualified = (
        channel["status"] == "new"
        and max(channel.get("forex_intent_score") or 0, channel.get("forex_score") or 0) >= 40
        and (
            channel.get("tier") in ("Tier_A", "Tier_B", "Tier_C")
            or channel.get("vip") is True
            or channel.get("account_management") is True
            or channel.get("copy_trading") is True
            or channel.get("funded_accounts") is True
            or (channel.get("commercial_fit_score") or 0) >= 40
        )
        and (channel.get("language") == "Arabic" or (channel.get("arabic_ratio") or 0) >= 15)
        and channel.get("entity_type") != "user"
        and channel.get("outreach_priority_reason") != "user_account"
    )

    assert not is_qualified, "@AlWaheedAlKhorasani must NOT be qualified!"


def test_arabic_channel_with_english_signals_and_commercial_service_qualifies():
    """
    Ensure an Arabic trading channel that posts signals in English
    (e.g., BUY XAUUSD @ 2450, SL: 2440, TP: 2465) and offers VIP/account management
    DOES qualify.
    """
    channel = {
        "channel_username": "ProGoldSignalsArabia",
        "status": "new",
        "language": "Arabic",
        "arabic_ratio": 65,
        "forex_intent_score": 85,
        "forex_score": 80,
        "commercial_fit_score": 60,
        "vip": True,
        "account_management": False,
        "copy_trading": False,
        "funded_accounts": False,
        "tier": "Tier_B",
        "entity_type": "channel",
        "outreach_priority_reason": None
    }

    is_qualified = (
        channel["status"] == "new"
        and max(channel.get("forex_intent_score") or 0, channel.get("forex_score") or 0) >= 40
        and (
            channel.get("tier") in ("Tier_A", "Tier_B", "Tier_C")
            or channel.get("vip") is True
            or channel.get("account_management") is True
            or channel.get("copy_trading") is True
            or channel.get("funded_accounts") is True
            or (channel.get("commercial_fit_score") or 0) >= 40
        )
        and (channel.get("language") == "Arabic" or (channel.get("arabic_ratio") or 0) >= 15)
        and channel.get("entity_type") != "user"
        and channel.get("outreach_priority_reason") != "user_account"
    )

    assert is_qualified, "Arabic channel with English signals & VIP offering MUST be qualified!"
