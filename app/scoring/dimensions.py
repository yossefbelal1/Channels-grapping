"""
app/scoring/dimensions.py — Channel Intelligence & Smart Ranking Model (Phase 3)

Comprehensive 12+ dimension lead scoring model without subscriber-count bias.
Relevance-driven scoring prioritizing Forex, Gold, Signal setups, and Arabic context.
Subscriber count and activity are ranking/context signals, NEVER hard qualification filters.
"""

from dataclasses import dataclass, asdict, field
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
import re

from app.discovery.arabic_normalizer import calculate_arabic_letter_ratio, normalize_arabic_text
from app.discovery.taxonomy import classify_text_taxonomy, KEYWORD_TAXONOMY
from app.scoring.growth_analyzer import GrowthAnalyzer

# Common Forex currency pairs and indices
CURRENCY_PAIRS = [
    "eurusd", "gbpusd", "usdjpy", "audusd", "usdcad", "nzdusd", "usdchf",
    "eurjpy", "gbpjpy", "eurgbp", "audjpy", "chfjpy", "cadjpy",
    "xauusd", "xagusd", "us30", "nas100", "nasdaq", "ger40", "dax", "spx500"
]

ARABIC_FOREX_TERMS = [
    "فوركس", "الفوركس", "تداول", "ذهب", "الذهب", "عملات", "توصيات", "تحليل",
    "صفقة", "صفقات", "شراء", "بيع", "هدف", "وقف الخسارة", "ستوب", "لوت", "بيب",
    "نقطة", "رافعة مالية", "سبريد", "حساب ممول", "إدارة محافظ", "نسخ صفقات"
]


@dataclass
class ScoringDimensions:
    forex_score: int = 0
    arabic_score: int = 0
    trading_score: int = 0
    signal_score: int = 0
    gold_score: int = 0
    activity_score: int = 0
    freshness_score: int = 0
    growth_score: int = 0
    commercial_score: int = 0
    contact_score: int = 0
    discovery_score: int = 0
    confidence_score: int = 0
    legitimacy_score: int = 100
    new_channel_score: int = 0
    member_count: int = 0
    classification: str = "POSSIBLE_FOREX"
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
    discovery_sources: Optional[List[str]] = None,
    first_seen_at: Optional[datetime] = None,
    last_post_at: Optional[datetime] = None,
    posts_24h: int = 0,
    posts_7d: int = 0,
    posts_30d: int = 0,
    avg_posts_per_day: Optional[float] = None,
    creation_date: Optional[datetime] = None,
    is_group: bool = False,
    snapshots: Optional[List[Dict[str, Any]]] = None
) -> ScoringDimensions:
    """
    Computes all Channel Intelligence dimensions without subscriber-count bias.
    Forex/Trading relevance is the primary signal supported by evidence.
    Subscriber count and activity are ranking/context signals, NOT hard gates.
    """
    recent_posts = recent_posts or []
    contact_types = contact_types or []
    discovery_sources = discovery_sources or []
    now = datetime.now(timezone.utc)

    # Clean combined texts
    bio_text = f"{title} {description}"
    all_text = f"{bio_text} " + " ".join(recent_posts[:60])
    lower_all = all_text.lower()
    norm_all = normalize_arabic_text(lower_all)

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Arabic Intelligence (0-100)
    # ──────────────────────────────────────────────────────────────────────────
    # Handles pure Arabic, mixed Arabic/English signals, and Arabic Forex vocabulary
    arabic_char_ratio = calculate_arabic_letter_ratio(all_text)
    arabic_vocab_matches = [w for w in ARABIC_FOREX_TERMS if w in norm_all]

    # Base score from character ratio
    arabic_score = int(arabic_char_ratio * 100)
    # Mixed-language boost: If channel has English trading setup but Arabic explanation/bio
    if arabic_char_ratio >= 0.15 and len(arabic_vocab_matches) >= 2:
        arabic_score = max(arabic_score, 65 + min(30, len(arabic_vocab_matches) * 5))
    elif arabic_char_ratio >= 0.05 and len(arabic_vocab_matches) >= 1:
        arabic_score = max(arabic_score, 45)
    elif len(arabic_vocab_matches) >= 3:
        arabic_score = max(arabic_score, 50)
    arabic_score = min(100, max(0, arabic_score))

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Multi-Post Taxonomy & Recurrence Analysis
    # ──────────────────────────────────────────────────────────────────────────
    # Global taxonomy scan
    tax_matches = classify_text_taxonomy(all_text)
    forex_terms = tax_matches.get("FOREX", [])
    gold_terms = tax_matches.get("GOLD_XAUUSD", [])
    signal_terms = tax_matches.get("SIGNALS", [])
    trading_terms = tax_matches.get("TRADING_STYLES", [])
    smc_terms = tax_matches.get("SMC_ICT", [])
    comm_terms = tax_matches.get("COMMERCIAL_SERVICES", [])
    prop_terms = tax_matches.get("PROP_FIRMS", [])

    # Per-post recurrence tracking: Count how many distinct posts contain Forex/Gold/Signal setups
    posts_with_forex = 0
    posts_with_signals = 0
    posts_with_gold = 0
    posts_total = max(1, len(recent_posts))

    for post in recent_posts:
        post_lower = post.lower()
        post_norm = normalize_arabic_text(post_lower)
        p_tax = classify_text_taxonomy(post)

        has_p_forex = bool(p_tax.get("FOREX") or any(pair in post_lower for pair in CURRENCY_PAIRS))
        has_p_signals = bool(p_tax.get("SIGNALS") or any(kw in post_lower for kw in ["buy", "sell", "sl", "tp", "شراء", "بيع", "هدف"]))
        has_p_gold = bool(p_tax.get("GOLD_XAUUSD") or "xauusd" in post_lower or "ذهب" in post_norm)

        if has_p_forex:
            posts_with_forex += 1
        if has_p_signals:
            posts_with_signals += 1
        if has_p_gold:
            posts_with_gold += 1

    # Currency pairs check
    pairs_matched = [p for p in CURRENCY_PAIRS if p in lower_all]

    # Bio-level intent
    bio_tax = classify_text_taxonomy(bio_text)
    bio_has_forex = bool(bio_tax.get("FOREX") or bio_tax.get("GOLD_XAUUSD") or any(p in bio_text.lower() for p in CURRENCY_PAIRS))

    # Single-keyword check: Did only 1 keyword appear once across posts and none in bio?
    total_distinct_forex_terms = len(forex_terms) + len(pairs_matched)
    is_isolated_single_keyword = (
        total_distinct_forex_terms == 1 and
        posts_with_forex <= 1 and
        not bio_has_forex and
        len(recent_posts) >= 5
    )

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Forex Intent Score (0 to 100) — Primary Signal
    # ──────────────────────────────────────────────────────────────────────────
    if is_isolated_single_keyword:
        forex_score = 15 # Kept low for isolated fluke mention
    else:
        # Scale based on vocabulary breadth + recurrence across posts
        term_breadth_score = min(60, len(forex_terms) * 12 + len(pairs_matched) * 10)
        recurrence_score = min(40, int((posts_with_forex / max(1, len(recent_posts))) * 60))
        if bio_has_forex:
            term_breadth_score = min(60, term_breadth_score + 15)
        forex_score = min(100, term_breadth_score + recurrence_score)

    # ──────────────────────────────────────────────────────────────────────────
    # 4. Gold / XAUUSD Score (0 to 100)
    # ──────────────────────────────────────────────────────────────────────────
    gold_breadth = len(gold_terms) * 18
    gold_recurrence = int((posts_with_gold / posts_total) * 50)
    if "xauusd" in lower_all or "ذهب" in norm_all:
        gold_breadth = max(30, gold_breadth)
    gold_score = min(100, gold_breadth + gold_recurrence)

    # ──────────────────────────────────────────────────────────────────────────
    # 5. Trading Methodology & SMC/ICT Score (0 to 100)
    # ──────────────────────────────────────────────────────────────────────────
    trading_score = min(100, (len(trading_terms) * 15) + (len(smc_terms) * 18))

    # ──────────────────────────────────────────────────────────────────────────
    # 6. Signals Score (0 to 100)
    # ──────────────────────────────────────────────────────────────────────────
    signal_breadth = len(signal_terms) * 15
    signal_recurrence = int((posts_with_signals / posts_total) * 50)
    # Check for SL/TP or target pattern
    has_sl_tp = bool(re.search(r'\b(sl|tp|stop\s*loss|take\s*profit|هدف|ستوب)\b', lower_all))
    if has_sl_tp:
        signal_breadth += 25
    signal_score = min(100, signal_breadth + signal_recurrence)

    # ──────────────────────────────────────────────────────────────────────────
    # 7. Commercial Context Score (0 to 100)
    # ──────────────────────────────────────────────────────────────────────────
    commercial_score = min(100, (len(comm_terms) * 15) + (len(prop_terms) * 15))

    # ──────────────────────────────────────────────────────────────────────────
    # 8. Contactability Context Score (0 to 100)
    # ──────────────────────────────────────────────────────────────────────────
    # Context signal only: contact != owner, lack of contact != reject
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

    # ──────────────────────────────────────────────────────────────────────────
    # 9. Activity Velocity Score (0 to 100) — Ranking Signal, NOT a gate
    # ──────────────────────────────────────────────────────────────────────────
    # Low activity != reject
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
    elif posts_7d >= 1:
        activity_score += 10

    if posts_30d >= 50:
        activity_score += 20
    elif posts_30d >= 10:
        activity_score += 10
    elif posts_30d >= 1:
        activity_score += 5

    # If channel has recent posts but low counts, give baseline
    if len(recent_posts) > 0 and activity_score == 0:
        activity_score = 15
    activity_score = min(100, max(5, activity_score))

    # ──────────────────────────────────────────────────────────────────────────
    # 10. Freshness Score (0 to 100) — Ranking Signal
    # ──────────────────────────────────────────────────────────────────────────
    freshness_score = 10
    freshness_hours = None
    if last_post_at:
        if last_post_at.tzinfo is None:
            last_post_at = last_post_at.replace(tzinfo=timezone.utc)
        freshness_hours = max(0.0, (now - last_post_at).total_seconds() / 3600.0)
        if freshness_hours <= 24.5:
            freshness_score = 100
        elif freshness_hours <= 72.5:
            freshness_score = 80
        elif freshness_hours <= 168.5: # 7 days
            freshness_score = 60
        elif freshness_hours <= 336.5: # 14 days
            freshness_score = 45
        elif freshness_hours <= 720.5: # 30 days
            freshness_score = 30
        else:
            freshness_score = 15
    elif posts_24h > 0:
        freshness_score = 90
    elif posts_7d > 0:
        freshness_score = 60
    elif posts_30d > 0:
        freshness_score = 35

    # ──────────────────────────────────────────────────────────────────────────
    # 11. Discovery Provenance Score (0 to 100)
    # ──────────────────────────────────────────────────────────────────────────
    unique_sources = set(discovery_sources) if discovery_sources else set()
    source_count = max(discovery_count, len(unique_sources))
    if source_count >= 4:
        discovery_score = 100
    elif source_count == 3:
        discovery_score = 80
    elif source_count == 2:
        discovery_score = 60
    else:
        discovery_score = 35

    # ──────────────────────────────────────────────────────────────────────────
    # 12. Growth Score (0 to 100) — Observed snapshots or 0 baseline
    # ──────────────────────────────────────────────────────────────────────────
    if snapshots and len(snapshots) >= 2:
        growth_score, growth_evidence = GrowthAnalyzer.calculate_growth_from_snapshots(snapshots)
    else:
        growth_score = 0 # No evidence -> 0 points
        growth_evidence = {
            "status": "UNOBSERVED_SNAPSHOTS",
            "snapshot_count": len(snapshots) if snapshots else 0,
            "growth_score": 0,
            "reason": "Historical snapshots not observed; assigned 0."
        }

    # ──────────────────────────────────────────────────────────────────────────
    # 13. Confidence Score (0 to 100) — Assessment Evidence Depth
    # ──────────────────────────────────────────────────────────────────────────
    confidence_points = 20 # baseline
    if len(recent_posts) >= 10:
        confidence_points += 25
    elif len(recent_posts) >= 3:
        confidence_points += 15

    if posts_with_forex >= 3:
        confidence_points += 25
    elif posts_with_forex >= 1:
        confidence_points += 15

    if bio_has_forex:
        confidence_points += 15
    if source_count >= 2:
        confidence_points += 15
    confidence_score = min(100, confidence_points)

    # ──────────────────────────────────────────────────────────────────────────
    # 14. Anti-Spam / Legitimacy Score (0 to 100)
    # ──────────────────────────────────────────────────────────────────────────
    legitimacy_score = 100
    spam_phrases = ["casino", "كازينو", "قمار", "betting", "مراهنات", "سكس", "اباحي", "شحن العاب", "hack"]
    found_spam = [sp for sp in spam_phrases if sp in lower_all]
    for _ in found_spam:
        legitimacy_score -= 35
    legitimacy_score = max(0, legitimacy_score)

    # ──────────────────────────────────────────────────────────────────────────
    # 15. New Channel Recognition (Context metadata, 0-100)
    # ──────────────────────────────────────────────────────────────────────────
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

    new_channel_score = min(100, new_channel_score)

    # ──────────────────────────────────────────────────────────────────────────
    # 16. Transparent Weighted Composite Score
    # ──────────────────────────────────────────────────────────────────────────
    # Core rule: Forex relevance is primary (80% of score across trading dimensions).
    # Subscriber count = 0% direct weight (pure neutrality across 400 to 2,000,000 members).
    # Activity = 5% weight (ranking context only, never a gate).
    weighted_sum = (
        (forex_score * 0.28) +
        (gold_score * 0.14) +
        (signal_score * 0.14) +
        (trading_score * 0.10) +
        (arabic_score * 0.10) +
        (activity_score * 0.05) +
        (freshness_score * 0.05) +
        (growth_score * 0.05) +
        (discovery_score * 0.04) +
        (commercial_score * 0.03) +
        (contact_score * 0.02) +
        (new_channel_score * 0.08)
    )

    # Apply anti-spam multiplier
    final_score = int(weighted_sum * (legitimacy_score / 100.0))
    final_score = max(0, min(100, final_score))

    # Damping for channels with completely zero trading/forex intent
    has_any_trading_intent = (
        forex_score > 0 or gold_score > 0 or signal_score > 0 or trading_score > 0 or
        bool(forex_terms or gold_terms or signal_terms or trading_terms or smc_terms or pairs_matched)
    )
    if not has_any_trading_intent:
        final_score = min(15, final_score)

    # ──────────────────────────────────────────────────────────────────────────
    # 17. Classification & Tier Assignment
    # ──────────────────────────────────────────────────────────────────────────
    if forex_score >= 60 and final_score >= 50 and arabic_score >= 15:
        classification = "HIGH_CONFIDENCE_FOREX"
    elif (forex_score >= 35 or gold_score >= 40 or signal_score >= 40) and final_score >= 35:
        classification = "LIKELY_FOREX"
    elif (forex_score >= 15 or gold_score >= 20 or signal_score >= 20 or trading_score >= 20) and final_score >= 20:
        classification = "POSSIBLE_FOREX"
    else:
        classification = "LOW_CONFIDENCE"

    # Tier mapping
    if final_score >= 75:
        tier = "Tier_A"
    elif final_score >= 55:
        tier = "Tier_B"
    elif final_score >= 35:
        tier = "Tier_C"
    else:
        tier = "Tier_D"

    # ──────────────────────────────────────────────────────────────────────────
    # 18. Structured Evidence Generation
    # ──────────────────────────────────────────────────────────────────────────
    evidence = {
        "forex_terms_matched": forex_terms,
        "currency_pairs_matched": pairs_matched,
        "gold_terms_matched": gold_terms,
        "signals_terms_matched": signal_terms,
        "trading_styles_matched": trading_terms,
        "smc_ict_matched": smc_terms,
        "commercial_terms_matched": comm_terms + prop_terms,
        "arabic_character_ratio": round(arabic_char_ratio, 4),
        "arabic_vocabulary_hits": arabic_vocab_matches,
        "posts_analyzed": len(recent_posts),
        "posts_with_forex": posts_with_forex,
        "posts_with_signals": posts_with_signals,
        "posts_with_gold": posts_with_gold,
        "is_isolated_single_keyword": is_isolated_single_keyword,
        "member_count": member_count,
        "activity_metrics": {
            "posts_24h": posts_24h,
            "posts_7d": posts_7d,
            "posts_30d": posts_30d,
            "avg_posts_per_day": avg_posts_per_day
        },
        "freshness_hours": round(freshness_hours, 1) if freshness_hours is not None else None,
        "growth_analysis": growth_evidence,
        "discovery_sources": list(unique_sources) if unique_sources else [f"count_{discovery_count}"],
        "spam_penalties": found_spam,
        "classification_reason": f"Classified as {classification} with Forex={forex_score}, Arabic={arabic_score}, Final={final_score}"
    }

    return ScoringDimensions(
        forex_score=forex_score,
        arabic_score=arabic_score,
        trading_score=trading_score,
        signal_score=signal_score,
        gold_score=gold_score,
        activity_score=activity_score,
        freshness_score=freshness_score,
        growth_score=growth_score,
        commercial_score=commercial_score,
        contact_score=contact_score,
        discovery_score=discovery_score,
        confidence_score=confidence_score,
        legitimacy_score=legitimacy_score,
        new_channel_score=new_channel_score,
        member_count=member_count,
        classification=classification,
        final_score=final_score,
        tier=tier,
        evidence=evidence
    )
