"""
app/discovery/relevance_evaluator.py — Multi-Signal Forensic Relevance Evaluator
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

from app.discovery.taxonomy import KEYWORD_TAXONOMY, classify_text_taxonomy
from app.discovery.arabic_normalizer import normalize_arabic_text, calculate_arabic_letter_ratio

logger = logging.getLogger(__name__)

# ── 1. Unambiguous Hard Disqualifiers ─────────────────────────────────────────
# Terms that represent 100% non-financial services (betting, gaming hacks, IPTV, spam).
# A channel matching any of these is rejected immediately with zero wasted API calls.
HARD_DISQUALIFIERS: List[str] = [
    # Sports Betting & Casinos
    "1xbet", "bet365", "betway", "melbet", "betwinner", "mostbet", "wolf bet",
    "كازينو", "casino", "مراهنات", "مراهنه", "سلوتس", "slots", "بوكر", "poker",
    "رهان", "رهانات", "bookmaker", "gambling",
    # Gaming & Gaming Accounts
    "شدات ببجي", "حسابات ببجي", "حسابات فورت", "حسابات فورتنايت", "شحن العاب", "شحن ألعاب",
    "جواهر فري", "pubg mobile", "free fire", "fortnite", "clash of clans",
    "clash royale", "robux", "roblox", "minecraft", "steam key", "nitro",
    # Pirated Media & Streaming Shops
    "iptv", "اشتراكات نتفلكس", "حسابات نتفليكس", "مسلسلات", "افلام", "كرتون",
    "انمي", "مانجا", "خلفيات", "رنات", "ستيكرز",
    # Channel Boost & Directory Spam
    "دعم قنوات", "زيادة متابعين", "زيادة أعضاء", "زيادة اعضاء", "تبادل نشر",
    "تبادل قنوات", "تبادل اشتراكات", "بوت اضافة", "اعضاء مجانا",
    # Underground / Hacking / Fraud
    "فيزا وهمية", "هكر", "بروكسي", "crack", "identity logs", "ssn"
]

# Common Currency Tickers and Trading Assets
CORE_CURRENCY_PAIRS: List[str] = [
    "xauusd", "xau/usd", "eurusd", "eur/usd", "gbpusd", "gbp/usd",
    "usdjpy", "usd/jpy", "usdcad", "usd/cad", "audusd", "aud/usd",
    "nzdusd", "nzd/usd", "usdchf", "usd/chf", "us30", "dow jones",
    "nas100", "nasdaq", "dax40", "dax", "sp500", "wti", "brent"
]

# Signal Technical Patterns
SIGNAL_SYNTAX_REGEX = re.compile(
    r'\b(sl\s*[:=-]?\s*\d+|tp\s*[:=-]?\s*\d+|tp[1-4]\s*[:=-]?\s*\d+|'
    r'entry\s*[:=-]?\s*\d+|stop\s*loss|take\s*profit|'
    r'هدف\s*[1-4]?|وقف\s*خسارة|دخول\s*صفقة|شراء\s*من|بيع\s*من)\b',
    re.IGNORECASE
)


@dataclass
class RelevanceDecision:
    """Detailed forensic verdict for a candidate channel."""
    is_qualified: bool
    relevance_score: int  # 0 to 100
    classification: str   # HIGH_CONFIDENCE_FOREX, LIKELY_FOREX, POSSIBLE_FOREX, REJECTED
    tier_estimate: str    # Tier_A, Tier_B, Tier_C, Tier_D
    target_queue: str     # queue:critical, queue:high, queue:normal
    evidence: Dict[str, Any] = field(default_factory=dict)
    rejection_reason: Optional[str] = None


class RelevanceEvaluator:
    """
    Multi-signal relevance and qualification evaluator.
    Combines taxonomy, currency pairs, technical syntax, and graph provenance.
    Never uses subscriber count or posting velocity as a hard blocker.
    """

    @staticmethod
    def is_hard_disqualified(text: str) -> Tuple[bool, Optional[str]]:
        """
        Fast triage: checks whether text contains unambiguous non-financial spam.
        """
        if not text:
            return False, None

        lower = text.lower()
        norm = normalize_arabic_text(lower)

        for disq in HARD_DISQUALIFIERS:
            if disq in lower or disq in norm:
                return True, disq
        return False, None

    @classmethod
    def evaluate(
        cls,
        title: str = "",
        description: str = "",
        username: str = "",
        recent_posts: Optional[List[str]] = None,
        referrer_is_tier_a: bool = False,
        discovery_source: str = "",
        in_degree: int = 0
    ) -> RelevanceDecision:
        """
        Performs holistic relevance evaluation across bio, recent messages, and graph context.
        """
        recent_posts = recent_posts or []
        username_clean = username.replace('_', ' ')
        combined_text = f"{title} {username_clean} {description} " + " ".join(recent_posts[:40])
        lower_combined = combined_text.lower()
        norm_combined = normalize_arabic_text(lower_combined)

        # ── 1. Fast Disqualification ──────────────────────────────────────────
        is_disq, matched_term = cls.is_hard_disqualified(f"{title} {username} {description}")
        if is_disq:
            return RelevanceDecision(
                is_qualified=False,
                relevance_score=0,
                classification="REJECTED",
                tier_estimate="Tier_D",
                target_queue="queue:normal",
                evidence={"disqualified_by": matched_term},
                rejection_reason=f"Matched hard disqualifier: {matched_term}"
            )

        # ── 2. Taxonomy Multi-Category Matches ────────────────────────────────
        tax_matches = classify_text_taxonomy(combined_text)
        forex_terms = tax_matches.get("FOREX", [])
        gold_terms = tax_matches.get("GOLD_XAUUSD", [])
        signals_terms = tax_matches.get("SIGNALS", [])
        smc_terms = tax_matches.get("SMC_ICT", [])
        comm_terms = tax_matches.get("COMMERCIAL_SERVICES", [])
        prop_terms = tax_matches.get("PROP_FIRMS", [])
        broker_terms = tax_matches.get("BROKERS_PLATFORMS", [])
        styles_terms = tax_matches.get("TRADING_STYLES", [])

        # ── 3. Asset Tickers & Currency Pairs ─────────────────────────────────
        pairs_found = [p for p in CORE_CURRENCY_PAIRS if p in lower_combined]

        # ── 4. Technical Signal Syntax (SL / TP / Entry) ──────────────────────
        signal_syntax_matches = SIGNAL_SYNTAX_REGEX.findall(combined_text)
        has_signal_syntax = len(signal_syntax_matches) > 0

        # ── 5. Arabic Trading Context ─────────────────────────────────────────
        arabic_ratio = calculate_arabic_letter_ratio(combined_text)
        has_arabic_context = arabic_ratio >= 0.10 or len(gold_terms) > 0 or len(forex_terms) > 0

        # ── 6. Compute Multi-Signal Score (0-100) ─────────────────────────────
        score = 0

        # Asset & pair signals (up to 35 pts)
        if len(pairs_found) >= 3:
            score += 35
        elif len(pairs_found) >= 1:
            score += 25
        elif "gold" in lower_combined or "ذهب" in norm_combined or "xau" in lower_combined or "forex" in lower_combined or "فوركس" in norm_combined:
            score += 25

        # Signal mechanics (up to 30 pts)
        if has_signal_syntax:
            score += 25
        if len(signals_terms) >= 2:
            score += 15
        elif len(signals_terms) >= 1:
            score += 10

        # Methodology (SMC / ICT / Scalping / Technical Analysis) (up to 25 pts)
        if len(smc_terms) >= 1:
            score += 15
        if len(styles_terms) >= 1:
            score += 10
        if "تحليل" in norm_combined or "chart" in lower_combined or "شارت" in norm_combined:
            score += 10

        # Commercial & Prop Firm Context (up to 20 pts)
        if len(comm_terms) >= 1 or "vip" in lower_combined:
            score += 15
        if len(prop_terms) >= 1 or len(broker_terms) >= 1:
            score += 10

        # Graph Provenance Prior (up to 25 pts boost)
        # Channels recommended by verified Tier A channels inherit high confidence
        if referrer_is_tier_a or discovery_source == "telegram_recommendations":
            score += 20
        if in_degree >= 2:
            score += 10

        score = min(100, score)

        # ── 7. Classification & Tiering ───────────────────────────────────────
        has_trading_evidence = (
            len(pairs_found) > 0 or
            has_signal_syntax or
            len(forex_terms) > 0 or
            len(gold_terms) > 0 or
            len(smc_terms) > 0 or
            (len(signals_terms) > 0 and len(comm_terms) > 0)
        )

        if score >= 65 and has_trading_evidence:
            classification = "HIGH_CONFIDENCE_FOREX"
            tier = "Tier_A"
            target_q = "queue:high"
            qualified = True
        elif score >= 45 and has_trading_evidence:
            classification = "LIKELY_FOREX"
            tier = "Tier_B"
            target_q = "queue:high"
            qualified = True
        elif score >= 25 and (has_trading_evidence or referrer_is_tier_a):
            classification = "POSSIBLE_FOREX"
            tier = "Tier_C"
            target_q = "queue:normal"
            qualified = True
        else:
            classification = "LOW_CONFIDENCE"
            tier = "Tier_D"
            target_q = "queue:normal"
            qualified = False

        evidence = {
            "score": score,
            "pairs_found": pairs_found,
            "signal_syntax_matches": len(signal_syntax_matches),
            "forex_terms_count": len(forex_terms),
            "gold_terms_count": len(gold_terms),
            "signals_terms_count": len(signals_terms),
            "smc_terms_count": len(smc_terms),
            "commercial_terms_count": len(comm_terms),
            "arabic_ratio": round(arabic_ratio, 2),
            "referrer_is_tier_a": referrer_is_tier_a,
            "in_degree": in_degree
        }

        return RelevanceDecision(
            is_qualified=qualified,
            relevance_score=score,
            classification=classification,
            tier_estimate=tier,
            target_queue=target_q,
            evidence=evidence,
            rejection_reason=None if qualified else "Insufficient trading evidence across bio, posts, and graph context"
        )
