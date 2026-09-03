"""
app/scoring/dimensions.py — 13-Dimension Lead Scoring Calculator with Evidence Tracking
"""

from dataclasses import dataclass, asdict, field
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from app.discovery.arabic_normalizer import calculate_arabic_letter_ratio, normalize_arabic_text
from app.discovery.taxonomy import classify_text_taxonomy
from app.scoring.growth_analyzer import GrowthAnalyzer


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
    evidence: Dict[str, Any] = field(default_factory=dict)

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
    is_group: bool = False,
    snapshots: Optional[List[Dict[str, Any]]] = None
) -> ScoringDimensions:
    """
    Computes all 13 scoring dimensions without subscriber-count bias.
    Actively rewards niche expertise, signal density, and new/growing channels.
    Stores classification evidence dictionary detailing reasons for scores.
    """
    recent_posts = recent_posts or []
    contact_types = contact_types or []
    all_text = f"{title} {description} " + " ".join(recent_posts[:50])

    # 1. Arabic NLP Score (0 to 100)
    arabic_ratio = calculate_arabic_letter_ratio(all_text)
    arabic_score = int(arabic_ratio * 100)

    # 2. Taxonomy Intent Classification
    tax_matches = classify_text_taxonomy(all_text)

    # 3. Forex Intent Score (0 to 100)
    forex_terms = tax_matches.get("FOREX", [])
    forex_score = min(100, len(forex_terms) * 15)

    # 4. Gold / XAUUSD Score (0 to 100)
    gold_terms = tax_matches.get("GOLD_XAUUSD", [])
    gold_score = min(100, len(gold_terms) * 20)

    # 5. Trading Methodology & SMC/ICT Score (0 to 100)
    trading_terms = tax_matches.get("TRADING_STYLES", [])
    smc_terms = tax_matches.get("SMC_ICT", [])
    trading_score = min(100, (len(trading_terms) * 12) + (len(smc_terms) * 18))

    # 6. Signals Score (0 to 100)
    signal_terms = tax_matches.get("SIGNALS", [])
    signal_score = min(100, len(signal_terms) * 18)

    # 7. Commercial Services Score (0 to 100)
    comm_terms = tax_matches.get("COMMERCIAL_SERVICES", [])
    prop_terms = tax_matches.get("PROP_FIRMS", [])
    commercial_score = min(100, (len(comm_terms) * 15) + (len(prop_terms) * 15))

    # 8. Contactability Score (0 to 100)
    contact_score = 0
    if has_contact:
        contact_score += 40
    if "owner" in contact_types or "admin" in contact_types:
        contact_score += 30
    if "whatsapp" in contact_types:
        contact_score += 20
    if "website" in contact_types or "linktree" in contact_types:
        contact_score += 10
    contact_score = min(100, contact_score)

    # 9. Activity Velocity Score (0 to 100)
    # Evaluates recent 24h/7d/30d posting frequency
    activity_score = 0
    if posts_24h >= 5:
        activity_score += 50
    elif posts_24h >= 1:
        activity_score += 30
    elif posts_7d >= 7:
        activity_score += 20

    if posts_7d >= 20:
        activity_score += 30
    elif posts_7d >= 5:
        activity_score += 15

    if posts_30d >= 50:
        activity_score += 20
    elif posts_30d >= 10:
        activity_score += 10
    activity_score = min(100, activity_score)

    # 10. Freshness Score (0 to 100)
    now = datetime.now(timezone.utc)
    freshness_score = 0
    if last_post_at:
        if last_post_at.tzinfo is None:
            last_post_at = last_post_at.replace(tzinfo=timezone.utc)
        hours_since_last = (now - last_post_at).total_seconds() / 3600.0
        if hours_since_last <= 24:
            freshness_score = 100
        elif hours_since_last <= 72:
            freshness_score = 80
        elif hours_since_last <= 168: # 7 days
            freshness_score = 50
        elif hours_since_last <= 720: # 30 days
            freshness_score = 25
        else:
            freshness_score = 5
    elif posts_24h > 0:
        freshness_score = 90
    elif posts_7d > 0:
        freshness_score = 60

    # 11. Multi-Source Discovery Confidence Score (0 to 100)
    discovery_score = min(100, 25 * max(1, discovery_count))

    # 12. New & Small Channel Prioritization Score (0 to 100)
    new_channel_score = 0
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

    # 13. Growth Score (Observed snapshots delta or fallback activity)
    if snapshots and len(snapshots) >= 2:
        growth_score, growth_evidence = GrowthAnalyzer.calculate_growth_from_snapshots(snapshots)
    else:
        growth_score = 50
        if posts_7d >= 10 and member_count >= 100:
            growth_score = min(100, 50 + int(posts_7d * 2))
        growth_evidence = {
            "status": "UNOBSERVED_SNAPSHOTS",
            "snapshot_count": len(snapshots) if snapshots else 0,
            "growth_score": growth_score
        }

    # 14. Legitimacy / Anti-Spam Score (0 to 100)
    legitimacy_score = 100
    lower_all = all_text.lower()
    spam_phrases = ["casino", "كازينو", "قمار", "betting", "مراهنات", "سكس", "اباحي", "شحن العاب", "hack"]
    found_spam = []
    for sp in spam_phrases:
        if sp in lower_all:
            legitimacy_score -= 35
            found_spam.append(sp)
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

    # Evidence breakdown
    evidence = {
        "forex_terms_matched": forex_terms,
        "gold_terms_matched": gold_terms,
        "signals_terms_matched": signal_terms,
        "trading_styles_matched": trading_terms,
        "smc_ict_matched": smc_terms,
        "arabic_character_ratio": round(arabic_ratio, 4),
        "small_channel_bonus_applied": (50 <= member_count <= 2000),
        "member_count": member_count,
        "growth_analysis": growth_evidence,
        "spam_penalties": found_spam,
        "discovery_sources_count": discovery_count
    }

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
        tier=tier,
        evidence=evidence
    )
