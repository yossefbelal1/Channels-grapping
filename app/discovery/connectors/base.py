"""
app/discovery/connectors/base.py — Unified Discovery Connector Interface

Provides base abstractions for free, rate-limited, fault-tolerant discovery
connectors across Telegram, TikTok, Facebook, and Web platforms.
"""

import re
import time
import random
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple, Set
import base64
import urllib.parse
from bs4 import BeautifulSoup
import requests
from app.discovery.entity_model import (
    Platform, EntityType, RelationType, CanonicalIdentity,
    DiscoveredEntity, DiscoveredRelationship
)

logger = logging.getLogger(__name__)

# Common cross-platform link regex patterns
TELEGRAM_LINK_REGEX = re.compile(
    r'(?:https?://)?(?:t\.me|telegram\.me)/(?:joinchat/)?\+?([a-zA-Z0-9_.-]{4,32})',
    re.IGNORECASE
)
TIKTOK_LINK_REGEX = re.compile(
    r'(?:https?://)?(?:www\.)?tiktok\.com/@([a-zA-Z0-9_.-]{2,32})',
    re.IGNORECASE
)
FACEBOOK_LINK_REGEX = re.compile(
    r'(?:https?://)?(?:www\.|m\.)?facebook\.com/(?:pages/|groups/)?([a-zA-Z0-9_.-]{3,64})',
    re.IGNORECASE
)
WHATSAPP_LINK_REGEX = re.compile(
    r'(?:https?://)?(?:wa\.me|api\.whatsapp\.com/send\?phone=)(\+?[0-9]{8,16})',
    re.IGNORECASE
)
WEB_URL_REGEX = re.compile(
    r'https?://(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+/[a-zA-Z0-9_.~!*\'();:@&=+$,/?%#-]*|[a-zA-Z0-9-]+\.[a-zA-Z]{2,})',
    re.IGNORECASE
)

STANDARD_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
]


@dataclass
class RateLimitPolicy:
    min_delay_seconds: float = 2.0
    max_delay_seconds: float = 6.0
    max_retries: int = 3
    backoff_factor: float = 1.8
    cooldown_after_rate_limit_seconds: int = 300


@dataclass
class ConnectorHealth:
    status: str = "HEALTHY"  # HEALTHY, DEGRADED, RATE_LIMITED, ERROR
    consecutive_failures: int = 0
    total_requests: int = 0
    total_successes: int = 0
    total_entities_discovered: int = 0
    last_success_at: Optional[datetime] = None
    last_error_at: Optional[datetime] = None
    last_error_message: Optional[str] = None
    cooldown_until: Optional[float] = None

    def is_cooling_down(self) -> bool:
        if self.cooldown_until:
            return time.time() < self.cooldown_until
        return False


@dataclass
class ConnectorSearchResult:
    entities: List[DiscoveredEntity] = field(default_factory=list)
    relationships: List[DiscoveredRelationship] = field(default_factory=list)
    next_cursor: Optional[str] = None
    has_more: bool = False
    query: str = ""
    platform: str = ""


class BaseDiscoveryConnector(ABC):
    """
    Abstract base connector for unified cross-platform discovery.
    """

    def __init__(
        self,
        name: str,
        platform: str,
        rate_limit_policy: Optional[RateLimitPolicy] = None,
        session: Optional[requests.Session] = None
    ):
        self.name = name
        self.platform = platform
        self.rate_policy = rate_limit_policy or RateLimitPolicy()
        self.health = ConnectorHealth()
        self.session = session or requests.Session()

    def is_healthy(self) -> bool:
        return self.health.status in ("HEALTHY", "DEGRADED") and not self.health.is_cooling_down()

    def record_success(self, entities_count: int = 0) -> None:
        self.health.total_requests += 1
        self.health.total_successes += 1
        self.health.consecutive_failures = 0
        self.health.total_entities_discovered += entities_count
        self.health.last_success_at = datetime.now(timezone.utc)
        if self.health.status != "HEALTHY":
            self.health.status = "HEALTHY"

    def record_failure(self, error_message: str, is_rate_limit: bool = False) -> None:
        self.health.total_requests += 1
        self.health.consecutive_failures += 1
        self.health.last_error_at = datetime.now(timezone.utc)
        self.health.last_error_message = error_message

        if is_rate_limit:
            self.health.status = "RATE_LIMITED"
            self.health.cooldown_until = time.time() + self.rate_policy.cooldown_after_rate_limit_seconds
            logger.warning(
                f"[{self.name}] Rate limit detected: {error_message}. Cooling down for {self.rate_policy.cooldown_after_rate_limit_seconds}s"
            )
        elif self.health.consecutive_failures >= 3:
            self.health.status = "DEGRADED"
            logger.warning(f"[{self.name}] Connector degraded: {self.health.consecutive_failures} consecutive failures.")

    def get_jittered_delay(self) -> float:
        return random.uniform(self.rate_policy.min_delay_seconds, self.rate_policy.max_delay_seconds)

    def fetch_public_url(self, url: str, timeout: int = 12) -> Optional[str]:
        """
        Safely fetches public web content using rotated user-agents and polite headers.
        """
        headers = {
            "User-Agent": random.choice(STANDARD_USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
            "Referer": "https://www.google.com/"
        }
        for attempt in range(1, self.rate_policy.max_retries + 1):
            try:
                resp = self.session.get(url, headers=headers, timeout=timeout)
                if resp.status_code == 200:
                    return resp.text
                elif resp.status_code in (429, 403):
                    self.record_failure(f"HTTP {resp.status_code}", is_rate_limit=(resp.status_code == 429))
                    time.sleep(self.rate_policy.backoff_factor * attempt)
                else:
                    logger.debug(f"[{self.name}] Non-200 status {resp.status_code} for {url}")
            except Exception as e:
                logger.debug(f"[{self.name}] Attempt {attempt} failed for {url}: {e}")
                time.sleep(self.rate_policy.backoff_factor * attempt)

        return None

    @staticmethod
    def decode_bing_url(href: str) -> str:
        """Decodes redirect-wrapped Bing search result URLs into the raw target URL."""
        if not href or "bing.com/ck/a" not in href:
            return href
        try:
            parsed = urllib.parse.urlparse(href)
            params = urllib.parse.parse_qs(parsed.query)
            u_vals = params.get("u", [])
            if not u_vals:
                return href
            u_val = u_vals[0]
            if u_val.startswith("a1"):
                raw_b64 = u_val[2:]
                rem = len(raw_b64) % 4
                if rem > 0:
                    raw_b64 += "=" * (4 - rem)
                return base64.b64decode(raw_b64).decode("utf-8", errors="ignore")
        except Exception:
            pass
        return href

    def search_bing_organic(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        """
        Executes free Bing search and decodes organic results.
        Returns [{'title': ..., 'url': ..., 'snippet': ...}].
        """
        url = f"https://www.bing.com/search?q={urllib.parse.quote_plus(query)}"
        html = self.fetch_public_url(url, timeout=8)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        results = []
        for li in soup.find_all("li", class_="b_algo"):
            h2 = li.find("h2")
            a = h2.find("a") if h2 else None
            snippet_div = li.find("div", class_="b_caption")
            if a:
                real_url = self.decode_bing_url(a.get("href", ""))
                title = a.get_text().strip()
                snippet = snippet_div.get_text().strip() if snippet_div else ""
                if real_url and not real_url.startswith(("javascript:", "#")):
                    results.append({
                        "title": title,
                        "url": real_url,
                        "snippet": snippet
                    })
            if len(results) >= limit:
                break
        return results

    def extract_cross_platform_links(
        self,
        text: str,
        source_canonical_id: str,
        source_platform: str
    ) -> Tuple[List[DiscoveredEntity], List[DiscoveredRelationship]]:
        """
        Scans raw text for links to other platforms and constructs entities and relationships.
        """
        if not text:
            return [], []

        entities: List[DiscoveredEntity] = []
        relationships: List[DiscoveredRelationship] = []
        seen_targets: Set[str] = set()

        # 1. Telegram Links
        tg_matches = TELEGRAM_LINK_REGEX.findall(text)
        GENERIC_TELEGRAM_IGNORES = {
            "joinchat", "share", "addlist", "bot", "username", "contact",
            "channel", "group", "admin", "help", "support", "s", "m", "c",
            "proxy", "socks", "login", "home", "privacy", "terms", "about"
        }
        for username in tg_matches:
            clean_u = username.strip().lstrip('@').lower()
            if clean_u and clean_u not in GENERIC_TELEGRAM_IGNORES and not clean_u.endswith("bot") and len(clean_u) >= 4:
                target_can = f"telegram:{clean_u}"
                if target_can != source_canonical_id and target_can not in seen_targets:
                    seen_targets.add(target_can)
                    ent = DiscoveredEntity(
                        platform=Platform.TELEGRAM,
                        entity_type=EntityType.CHANNEL,
                        canonical_id=target_can,
                        username=clean_u,
                        url=f"https://t.me/{clean_u}"
                    )
                    entities.append(ent)
                    rel = DiscoveredRelationship(
                        source_canonical_id=source_canonical_id,
                        target_canonical_id=target_can,
                        source_platform=source_platform,
                        target_platform=Platform.TELEGRAM,
                        relation_type=RelationType.LINK,
                        confidence=95,
                        evidence=f"Discovered via cross-platform link in {source_canonical_id}"
                    )
                    relationships.append(rel)

        # 2. TikTok Links
        tt_matches = TIKTOK_LINK_REGEX.findall(text)
        for tt_user in tt_matches:
            clean_tt = tt_user.strip().lstrip('@').lower()
            if clean_tt:
                target_can = f"tiktok:{clean_tt}"
                if target_can != source_canonical_id and target_can not in seen_targets:
                    seen_targets.add(target_can)
                    ent = DiscoveredEntity(
                        platform=Platform.TIKTOK,
                        entity_type=EntityType.ACCOUNT,
                        canonical_id=target_can,
                        username=clean_tt,
                        url=f"https://www.tiktok.com/@{clean_tt}"
                    )
                    entities.append(ent)
                    rel = DiscoveredRelationship(
                        source_canonical_id=source_canonical_id,
                        target_canonical_id=target_can,
                        source_platform=source_platform,
                        target_platform=Platform.TIKTOK,
                        relation_type=RelationType.SOCIAL_LINK,
                        confidence=95,
                        evidence=f"Discovered via social link in {source_canonical_id}"
                    )
                    relationships.append(rel)

        # 3. Facebook Links
        fb_matches = FACEBOOK_LINK_REGEX.findall(text)
        for fb_slug in fb_matches:
            clean_fb = fb_slug.strip().lower()
            if clean_fb and clean_fb not in ("pages", "groups", "share", "watch", "login"):
                target_can = f"facebook:{clean_fb}"
                if target_can != source_canonical_id and target_can not in seen_targets:
                    seen_targets.add(target_can)
                    ent = DiscoveredEntity(
                        platform=Platform.FACEBOOK,
                        entity_type=EntityType.PAGE,
                        canonical_id=target_can,
                        username=clean_fb,
                        url=f"https://www.facebook.com/{clean_fb}"
                    )
                    entities.append(ent)
                    rel = DiscoveredRelationship(
                        source_canonical_id=source_canonical_id,
                        target_canonical_id=target_can,
                        source_platform=source_platform,
                        target_platform=Platform.FACEBOOK,
                        relation_type=RelationType.SOCIAL_LINK,
                        confidence=95,
                        evidence=f"Discovered via social link in {source_canonical_id}"
                    )
                    relationships.append(rel)

        return entities, relationships

    @abstractmethod
    def search(self, query: str, cursor: Optional[str] = None) -> ConnectorSearchResult:
        """
        Executes search on platform and returns discovered entities and relationships.
        """
        pass
