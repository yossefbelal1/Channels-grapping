"""
app/scoring/dimensions.py — 13-Dimension Lead Scoring Calculator
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from app.discovery.arabic_normalizer import calculate_arabic_letter_ratio, normalize_arabic_text
from app.discovery.taxonomy import classify_text_taxonomy


@dataclass
class ScoringDimensions:
    forex_score: int = 0
    arabic_score: int = 0
    trading_score: int = 0
    signal_score: int = 0
    gold_score: int = 0
    activity_score: int = 0
    growth_score: int = 0
    commercial_score: int = 0
    contact_score: int = 0
    legitimacy_score: int = 100
    discovery_score: int = 0
    freshness_score: int = 0
    new_channel_score: int = 0
    final_score: int = 0
    tier: str = "Tier_D"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def calculate_all_dimensions(
    title: str = "",
    description: str = "",
    recent_posts: Optional[List[str]] = None,
    member_count: int = 0,
    has_contact: bool = False,
    contact_types: Optional[List[str]] = None,
    discovery_count: int = 1,
    first_seen_at: Optional[datetime] = None,
    last_post_at: Optional[datetime] = None,
    posts_24h: int = 0,
    posts_7d: int = 0,
    posts_30d: int = 0,
    creation_date: Optional[datetime] = None,
    is_group: bool = False
) -> ScoringDimensions:
    """
    Computes all 13 scoring dimensions without subscriber-count bias.
    Actively rewards niche expertise, signal density, and new/growing channels.
    """
    recent_posts = recent_posts or []
    contact_types = contact_types or []
    all_text = f"{title} {description} " + " ".join(recent_posts[:50])

    # 1. Arabic NLP Score (0 to 100)
    arabic_ratio = calculate_arabic_letter_ratio(all_text)
    arabic_score = int(arabic_ratio * 100)

    # 2. Taxonomy Breakdown
    tax_hits = classify_text_taxonomy(all_text)
    
    # 3. Core Forex Score (0 to 100)
    forex_hits = tax_hits.get("FOREX", 0)
    forex_score = min(100, forex_hits * 15)

    # 4. Trading / Technical Analysis Score (0 to 100)
    trading_hits = tax_hits.get("TRADING_STYLES", 0) + tax_hits.get("SMC_ICT", 0)
    trading_score = min(100, trading_hits * 18)

    # 5. Live Signals Score (0 to 100)
    signal_hits = tax_hits.get("SIGNALS", 0)
    signal_score = min(100, signal_hits * 20)

    # 6. Gold / XAUUSD Specialization Score (0 to 100)
    gold_hits = tax_hits.get("GOLD_XAUUSD", 0)
    gold_score = min(100, gold_hits * 22)

    # 7. Commercial & Business Offerings Score (0 to 100)
    commercial_hits = (
        tax_hits.get("COMMERCIAL_SERVICES", 0) +
        tax_hits.get("PROP_FIRMS", 0) +
        tax_hits.get("BROKERS_PLATFORMS", 0)
    )
    commercial_score = min(100, commercial_hits * 16)

    # 8. Contact Availability Score (0 to 100)
    contact_score = 0
    if has_contact:
        contact_score += 40
    if "whatsapp" in contact_types:
        contact_score += 25
    if "admin" in contact_types or "owner" in contact_types:
        contact_score += 20
    if "website" in contact_types:
        contact_score += 15
    contact_score = min(100, contact_score)

    # 9. Activity Score (0 to 100)
    activity_score = 0
    if posts_24h >= 3:
        activity_score += 50
    elif posts_24h >= 1:
        activity_score += 35
    elif posts_7d >= 5:
        activity_score += 25

    if posts_7d >= 15:
        activity_score += 30
    elif posts_7d >= 7:
        activity_score += 20

    if posts_30d >= 30:
        activity_score += 20
    activity_score = min(100, activity_score)

    # 10. Freshness Score (0 to 100)
    now = datetime.now(timezone.utc)
    freshness_score = 0
    if last_post_at:
        # Handle naive datetime
        if last_post_at.tzinfo is None:
            last_post_at = last_post_at.replace(tzinfo=timezone.utc)
        diff_hours = (now - last_post_at).total_seconds() / 3600.0
        if diff_hours <= 12:
            freshness_score = 100
        elif diff_hours <= 24:
            freshness_score = 85
        elif diff_hours <= 72:
            freshness_score = 60
        elif diff_hours <= 168: # 7 days
            freshness_score = 40
        else:
            freshness_score = 10

    # 11. Multi-Source Discovery Score (0 to 100)
    discovery_score = min(100, discovery_count * 25)

    # 12. Small & New Channel Prioritization Score (0 to 100)
    new_channel_score = 0
    # Channel age evaluation (boost if created in last 90 days or first seen recently)
    if creation_date:
        if creation_date.tzinfo is None:
            creation_date = creation_date.replace(tzinfo=timezone.utc)
        age_days = (now - creation_date).days
        if age_days <= 30:
            new_channel_score += 40
        elif age_days <= 90:
            new_channel_score += 25
    elif first_seen_at:
        if first_seen_at.tzinfo is None:
            first_seen_at = first_seen_at.replace(tzinfo=timezone.utc)
        seen_days = (now - first_seen_at).days
        if seen_days <= 14:
            new_channel_score += 30

    # Small active channel bonus (100 - 1500 members with active signals)
    if 50 <= member_count <= 2000 and (forex_score >= 30 or gold_score >= 30 or signal_score >= 30):
        new_channel_score += 50
    elif 2000 < member_count <= 5000 and (forex_score >= 20 or signal_score >= 20):
        new_channel_score += 30
    new_channel_score = min(100, new_channel_score)

    # 13. Growth Score (Default heuristic, enriched via snapshots)
    growth_score = 50
    if posts_7d >= 10 and member_count >= 100:
        growth_score = min(100, 50 + int(posts_7d * 2))

    # 14. Legitimacy / Anti-Spam Score (0 to 100)
    legitimacy_score = 100
    lower_all = all_text.lower()
    spam_phrases = ["casino", "كازينو", "قمار", "betting", "مراهنات", "سكس", "اباحي", "شحن العاب", "hack"]
    for sp in spam_phrases:
        if sp in lower_all:
            legitimacy_score -= 35
    legitimacy_score = max(0, legitimacy_score)

    # ── Weighted Final Score ──────────────────────────────────────────────────
    # Weighted composite prioritizing Forex intent and Arabic relevance over subscriber count
    weighted_sum = (
        (forex_score * 0.25) +
        (gold_score * 0.15) +
        (signal_score * 0.15) +
        (trading_score * 0.12) +
        (arabic_score * 0.12) +
        (commercial_score * 0.08) +
        (contact_score * 0.08) +
        (growth_score * 0.05) +
        (activity_score * 0.05) +
        (freshness_score * 0.05) +
        (new_channel_score * 0.20) # Bonus multiplier for small & new active channels
    )

    # Scale legitimacy penalty
    final_score = int(weighted_sum * (legitimacy_score / 100.0))
    final_score = max(0, min(100, final_score))

    # Tier Classification
    if final_score >= 80:
        tier = "Tier_A"
    elif final_score >= 60:
        tier = "Tier_B"
    elif final_score >= 40:
        tier = "Tier_C"
    else:
        tier = "Tier_D"

    return ScoringDimensions(
        forex_score=forex_score,
        arabic_score=arabic_score,
        trading_score=trading_score,
        signal_score=signal_score,
        gold_score=gold_score,
        activity_score=activity_score,
        growth_score=growth_score,
        commercial_score=commercial_score,
        contact_score=contact_score,
        legitimacy_score=legitimacy_score,
        discovery_score=discovery_score,
        freshness_score=freshness_score,
        new_channel_score=new_channel_score,
        final_score=final_score,
        tier=tier
    )
