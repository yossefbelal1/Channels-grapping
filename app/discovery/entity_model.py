"""
app/discovery/entity_model.py — Unified Cross-Platform Entity & Relationship Model

Defines normalized entity types, platforms, canonical identity generation,
and relationship structures for cross-platform discovery (Telegram, TikTok, Facebook, Web).
"""

import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Set, Tuple


class Platform:
    TELEGRAM = "telegram"
    TIKTOK = "tiktok"
    FACEBOOK = "facebook"
    WEB = "web"

    ALL = [TELEGRAM, TIKTOK, FACEBOOK, WEB]


class EntityType:
    CHANNEL = "channel"
    ACCOUNT = "account"
    PAGE = "page"
    VIDEO = "video"
    POST = "post"
    WEBSITE = "website"

    ALL = [CHANNEL, ACCOUNT, PAGE, VIDEO, POST, WEBSITE]


class RelationType:
    LINK = "link"
    MENTION = "mention"
    FORWARDED_FROM = "forwarded_from"
    PROMOTED = "promoted"
    RECOMMENDATION = "recommendation"
    SOCIAL_LINK = "social_link"
    EXTERNAL_SITE = "external_site"

    ALL = [LINK, MENTION, FORWARDED_FROM, PROMOTED, RECOMMENDATION, SOCIAL_LINK, EXTERNAL_SITE]


class CandidateStatus:
    DISCOVERED = "discovered"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    REJECTED = "rejected"
    EXPANDED = "expanded"

    ALL = [DISCOVERED, VERIFYING, VERIFIED, REJECTED, EXPANDED]


GENERIC_DOMAIN_BLACKLIST: Set[str] = {
    "google.com", "bing.com", "yahoo.com", "duckduckgo.com", "yandex.com",
    "wikipedia.org", "wikimedia.org", "amazon.com", "amazon.fr", "amazon.co.uk", "amazon.de",
    "apple.com", "microsoft.com", "cloudflare.com", "youtube.com", "youtu.be",
    "twitter.com", "x.com", "instagram.com", "linkedin.com", "pinterest.com",
    "reddit.com", "quora.com", "medium.com", "github.com", "gitlab.com",
    "play.google.com", "apps.apple.com", "support.google.com"
}

GENERIC_HANDLE_BLACKLIST: Set[str] = {
    "help", "support", "admin", "login", "register", "privacy", "terms",
    "contact", "about", "rules", "faq", "share", "channel", "group",
    "joinchat", "addlist", "bot", "proxy", "socks", "home", "search",
    "user", "profile", "settings", "notifications"
}


FINANCIAL_FOREX_KEYWORDS: List[str] = [
    # Arabic high-intent trading / forex terms
    "تداول", "فوركس", "ذهب", "عملات", "أسهم", "توصيات", "تحليل فني", "إشارات",
    "صفقات", "حساب إسلامي", "حساب اسلامي", "رافعة مالية", "سكالبينج", "سوينج",
    "أكاديمية تداول", "اكاديمية تداول", "نسخ صفقات", "إدارة محافظ", "ادارة محافظ",
    "مؤشرات", "بونص تداول", "سوق العملات", "تداول الذهب", "توصيات vip",
    # English terms
    "forex", "trading", "gold", "xauusd", "crypto", "signals", "broker",
    "pips", "daytrading", "investing", "scalping", "swing trading", "prop firm",
    "funded account", "copy trading", "technical analysis", "stocks", "market analysis"
]


def evaluate_candidate_relevance(title: str = "", description: str = "", raw_text: str = "") -> Tuple[bool, int, List[str]]:
    """
    Evaluates whether a candidate profile, page, or website is genuinely related
    to Forex, Gold, or Financial Trading.
    Returns: (is_relevant: bool, relevance_score: int 0-100, matched_terms: List[str])
    """
    corpus = f"{title} {description} {raw_text}".lower()
    if not corpus.strip():
        return False, 0, []

    matched = []
    for kw in FINANCIAL_FOREX_KEYWORDS:
        if kw in corpus:
            matched.append(kw)

    if not matched:
        return False, 0, []

    # Score calculation: 20 pts base + 10 pts per additional unique term (capped at 100)
    score = min(100, 20 + len(matched) * 10)
    return True, score, matched


class CanonicalIdentity:
    """
    Generates deterministic, deduplicated canonical identifiers across platforms.
    """

    @staticmethod
    def clean_telegram(identifier: str) -> str:
        if not identifier:
            return ""
        clean = identifier.strip()
        # Handle URLs
        clean = re.sub(r'^https?://(?:www\.)?(?:t\.me|telegram\.me)/', '', clean, flags=re.IGNORECASE)
        clean = clean.lstrip('@').split('?')[0].strip('/').strip()
        # Remove joinchat prefix if public channel
        if clean.startswith('joinchat/'):
            return clean.lower()
        return clean.lower()

    @staticmethod
    def clean_tiktok(identifier: str) -> str:
        if not identifier:
            return ""
        clean = identifier.strip()
        # Handle URLs: https://www.tiktok.com/@username/video/123 -> username
        clean = re.sub(r'^https?://(?:www\.)?tiktok\.com/', '', clean, flags=re.IGNORECASE)
        clean = clean.lstrip('@').split('?')[0].split('/')[0].strip()
        return clean.lower()

    @staticmethod
    def clean_facebook(identifier: str) -> str:
        if not identifier:
            return ""
        clean = identifier.strip()
        # Handle URLs: https://www.facebook.com/pagename/ -> pagename
        clean = re.sub(r'^https?://(?:www\.|m\.)?facebook\.com/', '', clean, flags=re.IGNORECASE)
        clean = clean.split('?')[0].strip('/')
        # Handle groups or pages paths
        if clean.startswith('groups/'):
            clean = clean.split('/')[1] if len(clean.split('/')) > 1 else clean
        elif clean.startswith('pages/'):
            parts = clean.split('/')
            clean = parts[-1] if parts[-1] else (parts[-2] if len(parts) > 1 else clean)
        else:
            clean = clean.split('/')[0]
        return clean.lower()

    @staticmethod
    def clean_web(url: str) -> str:
        if not url:
            return ""
        clean = url.strip()
        if not clean.startswith(('http://', 'https://')):
            clean = 'https://' + clean
        parsed = urllib.parse.urlparse(clean)
        netloc = parsed.netloc.lower()
        if netloc.startswith('www.'):
            netloc = netloc[4:]
        # Retain path without query or trailing slash for clean identity
        path = parsed.path.rstrip('/')
        return f"{netloc}{path}".strip()

    @classmethod
    def generate(cls, platform: str, identifier: str) -> str:
        """
        Generates canonical ID string e.g. 'telegram:ozarktrade', 'tiktok:salimforex'.
        """
        plat = platform.lower().strip()
        if plat == Platform.TELEGRAM:
            cleaned = cls.clean_telegram(identifier)
            return f"telegram:{cleaned}" if cleaned else ""
        elif plat == Platform.TIKTOK:
            cleaned = cls.clean_tiktok(identifier)
            return f"tiktok:{cleaned}" if cleaned else ""
        elif plat == Platform.FACEBOOK:
            cleaned = cls.clean_facebook(identifier)
            return f"facebook:{cleaned}" if cleaned else ""
        elif plat == Platform.WEB:
            cleaned = cls.clean_web(identifier)
            return f"web:{cleaned}" if cleaned else ""
        else:
            cleaned = identifier.strip().lower()
            return f"{plat}:{cleaned}" if cleaned else ""


@dataclass
class DiscoveredEntity:
    """
    Unified representation of a discovered entity across any platform.
    """
    platform: str
    entity_type: str
    canonical_id: str
    username: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    url: str = ""
    follower_count: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw_content: Optional[str] = None
    depth: int = 0
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        if not self.canonical_id and self.username:
            self.canonical_id = CanonicalIdentity.generate(self.platform, self.username)
        elif not self.canonical_id and self.url:
            self.canonical_id = CanonicalIdentity.generate(self.platform, self.url)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "platform": self.platform,
            "entity_type": self.entity_type,
            "canonical_id": self.canonical_id,
            "username": self.username,
            "title": self.title,
            "description": self.description,
            "url": self.url,
            "follower_count": self.follower_count,
            "metadata": self.metadata,
            "depth": self.depth,
            "discovered_at": self.discovered_at.isoformat() if self.discovered_at else None
        }


@dataclass
class DiscoveredRelationship:
    """
    Directed relationship edge between two entities across platforms.
    """
    source_canonical_id: str
    target_canonical_id: str
    source_platform: str
    target_platform: str
    relation_type: str
    confidence: int = 100
    evidence: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_canonical_id": self.source_canonical_id,
            "target_canonical_id": self.target_canonical_id,
            "source_platform": self.source_platform,
            "target_platform": self.target_platform,
            "relation_type": self.relation_type,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "metadata": self.metadata
        }


@dataclass
class DiscoveryCandidate:
    """
    Normalized candidate data contract across all platforms.
    Every platform (Telegram, TikTok, Facebook, Web) produces candidates conforming
    to this contract before entering the verification and relevance pipeline.
    """
    platform: str
    native_identifier: str
    canonical_id: str
    canonical_url: str
    source_entity: Optional[str] = None
    discovery_method: str = "search"
    provenance: Dict[str, Any] = field(default_factory=dict)
    evidence: str = ""
    confidence: int = 100
    relationship_type: str = RelationType.LINK
    status: str = CandidateStatus.DISCOVERED
    relevance_score: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_entity(self, title: str = "", description: str = "") -> DiscoveredEntity:
        e_type = EntityType.CHANNEL if self.platform == Platform.TELEGRAM else (
            EntityType.PAGE if self.platform == Platform.FACEBOOK else (
                EntityType.ACCOUNT if self.platform == Platform.TIKTOK else EntityType.WEBSITE
            )
        )
        return DiscoveredEntity(
            platform=self.platform,
            entity_type=e_type,
            canonical_id=self.canonical_id,
            username=self.native_identifier,
            title=title,
            description=description,
            url=self.canonical_url,
            metadata=self.metadata,
            discovered_at=self.discovered_at
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "platform": self.platform,
            "native_identifier": self.native_identifier,
            "canonical_id": self.canonical_id,
            "canonical_url": self.canonical_url,
            "source_entity": self.source_entity,
            "discovery_method": self.discovery_method,
            "provenance": self.provenance,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "relationship_type": self.relationship_type,
            "status": self.status,
            "relevance_score": self.relevance_score,
            "metadata": self.metadata,
            "discovered_at": self.discovered_at.isoformat() if self.discovered_at else None
        }
