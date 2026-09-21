"""
app/discovery/exchange_analyzer.py — Exchange & Cross-Promotion Affinity Engine

Evaluates Telegram channels as potential active nodes in a mutual exchange & cross-promotion network:
1. Exchange Affinity Score (0-100): Evidence of shoutouts, mutual forwards, peer mentions, and promo phrases.
2. Growth / Size Sweet Spot Score (0-100): Peak receptivity in small-to-mid channels (1k–35k).
3. Network Value Score (0-100): Graph centrality, reciprocal edges, and cluster bridging.
4. Exchange Network Seed & Hub Qualifications.
"""

import re
import logging
from typing import Dict, Any, List, Optional, Tuple, Set
from datetime import datetime, timezone

logger = logging.getLogger("exchange_analyzer")

# ── Semantic & Pattern Dictionaries for Exchange & Cross-Promotion ────────────
EXCHANGE_PHRASES_AR = [
    r"\bتبادل\b",
    r"\bتبادل\s+إعلاني\b",
    r"\bتبادل\s+اعلاني\b",
    r"\bتبادل\s+نشر\b",
    r"\bقناة\s+صديقة\b",
    r"\bقنوات\s+صديقة\b",
    r"\bقناة\s+شقيقة\b",
    r"\bشراكة\b",
    r"\bدعم\s+القنوات\b",
    r"\bنوصي\s+بمتابعة\b",
    r"\bنوصي\s+بها\b",
    r"\bقناة\s+ننصح\s+بها\b",
    r"\bمن\s+أفضل\s+القنوات\b",
    r"\bمن\s+افضل\s+القنوات\b",
    r"\bمن\s+أقوى\s+القنوات\b",
    r"\bمن\s+اقوى\s+القنوات\b",
    r"\bبرعاية\b",
    r"\bإعلان\s+مؤقت\b",
    r"\bاعلان\s+مؤقت\b",
    r"\bإعلان\s+مدفوع\b",
    r"\bاعلان\s+مدفوع\b",
    r"\bتابعوا\s+هذه\s+القناة\b",
    r"\bتابعوا\s+القناة\b",
    r"\bانضموا\s+إلى\s+القناة\b",
    r"\bانضموا\s+الى\s+القناة\b",
    r"\bكروس\s+بروموشن\b",
    r"\bشوت\s+اوت\b",
    r"\bللإعلان\s+والتبادل\b",
    r"\bللاعلان\s+والتبادل\b",
    r"\bللاشتراك\s+بالدعم\b",
]

EXCHANGE_PHRASES_EN = [
    r"\bcross[- ]?promo(?:tion)?\b",
    r"\bshoutout\b",
    r"\bmutual\s+promo(?:tion)?\b",
    r"\bpartner\s+channel\b",
    r"\brecommended\s+channel\b",
    r"\bsponsored\s+post\b",
    r"\bpaid\s+ad\b",
    r"\bfor\s+promo(?:tion)?\s+contact\b",
    r"\bpromo\s+exchange\b",
    r"\badvertise\s+with\s+us\b",
]

COMPILED_EXCHANGE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in (EXCHANGE_PHRASES_AR + EXCHANGE_PHRASES_EN)
]

TELEGRAM_LINK_RE = re.compile(
    r'(?:https?://)?(?:t\.me|telegram\.me)/(?:joinchat/)?\+?([a-zA-Z0-9_.-]{4,35})',
    re.IGNORECASE
)
MENTION_RE = re.compile(r'@([a-zA-Z0-9_]{4,35})')

JUNK_HANDLES = {
    'joinchat', 'share', 'addstickers', 'addlist', 'gmail', 'hotmail',
    'yahoo', 'outlook', 'icloud', 'mail', 'telegram', 'spambot', 'bot',
    'username', 'ads', 'support', 'help', 'admin', 'contact', 'info',
    'feedback', 'terms', 'privacy'
}


class ExchangeAffinityAnalyzer:
    """
    Evaluates channels along the dimensions of mutual exchange readiness,
    growth openness, and network value.
    """

    @staticmethod
    def calculate_size_sweet_spot(member_count: int) -> Tuple[int, str]:
        """
        Scores subscriber size based on mutual exchange receptivity.
        Small and mid-sized channels (1,000–35,000) have the highest need for growth
        and highest willingness to cross-promote without charging heavy fees.
        """
        if member_count <= 0:
            return 30, "unknown_size"

        if 2_000 <= member_count <= 15_000:
            return 100, "optimal_prime_sweet_spot (2k-15k)"
        elif 1_000 <= member_count < 2_000:
            return 85, "optimal_growing_sweet_spot (1k-2k)"
        elif 15_000 < member_count <= 35_000:
            return 85, "optimal_established_sweet_spot (15k-35k)"
        elif 500 <= member_count < 1_000:
            return 70, "early_stage_promising (500-1k)"
        elif 35_000 < member_count <= 60_000:
            return 55, "upper_mid_size (35k-60k)"
        elif 60_000 < member_count <= 100_000:
            return 35, "large_channel_commercial (60k-100k)"
        elif member_count > 100_000:
            return 20, "giant_low_exchange_receptivity (>100k)"
        else: # < 500
            return 40, "micro_channel (<500)"

    @classmethod
    def analyze_exchange_affinity(
        cls,
        title: str = "",
        description: str = "",
        pinned_text: str = "",
        recent_messages: Optional[List[Any]] = None,
        member_count: int = 0,
        contact_username: Optional[str] = None,
        has_verified_contact: bool = False,
        in_degree: int = 0,
        out_degree: int = 0,
        relation_types: Optional[Set[str]] = None,
        edge_evidence_list: Optional[List[str]] = None,
        forex_relevance_score: int = 0
    ) -> Dict[str, Any]:
        """
        Comprehensive multi-surface analysis producing:
        - exchange_affinity_score (0-100)
        - growth_openness_score (0-100)
        - network_value_score (0-100)
        - is_exchange_seed (bool)
        - is_exchange_hub (bool)
        - structured evidence payload
        """
        recent_messages = recent_messages or []
        relation_types = relation_types or set()
        edge_evidence_list = edge_evidence_list or []

        # 1. Normalize text surfaces
        desc_norm = description or ""
        pinned_norm = pinned_text or ""
        combined_header = f"{title} {desc_norm} {pinned_norm}"

        # 2. Extract message texts and forward origins
        msg_texts: List[str] = []
        forwarded_count = 0
        forward_origins: Set[str] = set()
        peer_mentions: Set[str] = set()
        outbound_channel_links: Set[str] = set()

        clean_contact = (contact_username or "").lower().lstrip('@')

        for m in recent_messages:
            text = ""
            if isinstance(m, str):
                text = m
            elif isinstance(m, dict):
                text = m.get("message") or m.get("text") or ""
                if m.get("fwd_from") or m.get("forward"):
                    forwarded_count += 1
                    fwd = m.get("fwd_from") or m.get("forward")
                    if isinstance(fwd, dict):
                        orig = fwd.get("from_name") or fwd.get("channel_username") or fwd.get("channel_id")
                        if orig:
                            forward_origins.add(str(orig).lower())
            elif hasattr(m, "message"):
                text = getattr(m, "message", "") or ""
                if getattr(m, "fwd_from", None) or getattr(m, "forward", None):
                    forwarded_count += 1
                    fwd = getattr(m, "fwd_from", None) or getattr(m, "forward", None)
                    orig_name = getattr(fwd, "from_name", None)
                    orig_id = getattr(fwd, "channel_id", None)
                    if orig_name:
                        forward_origins.add(str(orig_name).lower())
                    elif orig_id:
                        forward_origins.add(str(orig_id))

            if text:
                msg_texts.append(text)

                # Scan for peer mentions (@mention)
                for men in MENTION_RE.findall(text):
                    men_clean = men.lower()
                    if (
                        men_clean not in JUNK_HANDLES
                        and men_clean != clean_contact
                        and not men_clean.endswith("bot")
                    ):
                        peer_mentions.add(men_clean)

                # Scan for outbound t.me links
                for lnk in TELEGRAM_LINK_RE.findall(text):
                    lnk_clean = lnk.lower().lstrip('+')
                    if lnk_clean not in JUNK_HANDLES and lnk_clean != clean_contact:
                        outbound_channel_links.add(lnk_clean)

        total_posts = max(1, len(msg_texts))
        all_post_content = " ".join(msg_texts)
        full_corpus = f"{combined_header} {all_post_content}"

        # 3. Match Exchange / Promotion Markers
        matched_phrases: List[str] = []
        for pattern in COMPILED_EXCHANGE_PATTERNS:
            matches = pattern.findall(full_corpus)
            if matches:
                matched_phrases.append(pattern.pattern.replace(r"\b", "").replace(r"\s+", " "))

        # Count how many distinct posts contain promotion markers
        posts_with_promo = 0
        for p_text in msg_texts:
            if any(pat.search(p_text) for pat in COMPILED_EXCHANGE_PATTERNS):
                posts_with_promo += 1

        # 4. Compute Exchange Affinity Score (0-100)
        # Factor A: Explicit promotion / exchange language (0-40 pts)
        phrase_pts = min(40, len(matched_phrases) * 12)

        # Factor B: Outbound peer channel mentions & links (0-25 pts)
        distinct_peers = len(peer_mentions.union(outbound_channel_links))
        if distinct_peers >= 5:
            peer_pts = 25
        elif distinct_peers >= 3:
            peer_pts = 20
        elif distinct_peers >= 1:
            peer_pts = 12
        else:
            peer_pts = 0

        # Factor C: Forward syndication behavior (0-20 pts)
        fwd_ratio = forwarded_count / total_posts
        if len(forward_origins) >= 3 or fwd_ratio >= 0.15:
            fwd_pts = 20
        elif len(forward_origins) >= 1 or forwarded_count >= 2:
            fwd_pts = 12
        elif forwarded_count >= 1:
            fwd_pts = 6
        else:
            fwd_pts = 0

        # Factor D: Recurrence of promotions across posts (0-15 pts)
        if posts_with_promo >= 3:
            recurrence_pts = 15
        elif posts_with_promo >= 1:
            recurrence_pts = 8
        else:
            recurrence_pts = 0

        # Graph relation boost (if graph_edges already confirm promo / recommendation / forward)
        graph_promo_boost = 0
        rel_lower = {str(r).lower() for r in relation_types}
        if "promoted" in rel_lower or "advertisement" in rel_lower:
            graph_promo_boost += 15
        if "forwarded_from" in rel_lower or "forward" in rel_lower:
            graph_promo_boost += 10
        if "recommendation" in rel_lower:
            graph_promo_boost += 10

        raw_affinity = phrase_pts + peer_pts + fwd_pts + recurrence_pts + graph_promo_boost
        exchange_affinity_score = max(0, min(100, raw_affinity))

        # 5. Compute Growth & Size Sweet Spot Score (0-100)
        growth_openness_score, size_bracket = cls.calculate_size_sweet_spot(member_count)

        # 6. Compute Network Value Score (0-100)
        # Combines graph degree, peer links, and diversity of connections
        net_pts = 0
        total_degree = in_degree + out_degree
        if total_degree >= 10:
            net_pts += 40
        elif total_degree >= 5:
            net_pts += 30
        elif total_degree >= 2:
            net_pts += 20
        elif total_degree >= 1:
            net_pts += 10

        if len(relation_types) >= 3:
            net_pts += 25
        elif len(relation_types) >= 1:
            net_pts += 15

        if distinct_peers >= 3:
            net_pts += 20
        elif distinct_peers >= 1:
            net_pts += 10

        if len(forward_origins) >= 2:
            net_pts += 15

        network_value_score = max(0, min(100, net_pts))

        # 7. Evaluate Exchange Network Seed & Hub status
        # An Exchange Network Seed is:
        # - Relevant trading channel (Forex score >= 35)
        # - Medium/Small sweet spot (growth_openness >= 60, i.e. 500 to 35k)
        # - Tangible exchange affinity (affinity >= 35 or distinct_peers >= 2 or promo phrases)
        # - Has verified contact
        is_exchange_seed = bool(
            forex_relevance_score >= 35
            and growth_openness_score >= 60
            and (exchange_affinity_score >= 35 or len(matched_phrases) >= 1 or distinct_peers >= 2)
            and has_verified_contact
        )

        # An Exchange Hub is a channel that actively and repeatedly links/forwards/promotes multiple trading channels
        is_exchange_hub = bool(
            exchange_affinity_score >= 50
            and (distinct_peers >= 4 or total_degree >= 4 or len(forward_origins) >= 3)
        )

        evidence = {
            "exchange_affinity_score": exchange_affinity_score,
            "growth_openness_score": growth_openness_score,
            "network_value_score": network_value_score,
            "size_bracket": size_bracket,
            "is_exchange_seed": is_exchange_seed,
            "is_exchange_hub": is_exchange_hub,
            "matched_exchange_phrases": matched_phrases[:10],
            "distinct_peer_count": distinct_peers,
            "sample_peer_mentions": list(peer_mentions)[:8],
            "sample_channel_links": list(outbound_channel_links)[:8],
            "forwarded_post_count": forwarded_count,
            "forward_ratio": round(fwd_ratio, 3),
            "forward_origins": list(forward_origins)[:8],
            "posts_with_promotions": posts_with_promo,
            "posts_analyzed": len(msg_texts),
            "graph_metrics": {
                "in_degree": in_degree,
                "out_degree": out_degree,
                "relations": list(relation_types)
            }
        }

        return {
            "exchange_affinity_score": exchange_affinity_score,
            "growth_openness_score": growth_openness_score,
            "network_value_score": network_value_score,
            "is_exchange_seed": is_exchange_seed,
            "is_exchange_hub": is_exchange_hub,
            "evidence": evidence
        }
