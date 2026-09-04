"""
app/discovery/connectors/tiktok.py — Free Public TikTok Discovery Connector

Discovers public TikTok Forex/trading creators, profiles, videos, and bio links
using free legitimate public search indexing and public profile parsing.
Extracts cross-platform bridges (TikTok -> Telegram, TikTok -> Facebook, TikTok -> Website).
"""

import re
import json
import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from bs4 import BeautifulSoup

from app.discovery.entity_model import (
    Platform, EntityType, RelationType, CanonicalIdentity,
    DiscoveredEntity, DiscoveredRelationship, evaluate_candidate_relevance
)
from app.discovery.connectors.base import (
    BaseDiscoveryConnector, ConnectorSearchResult, RateLimitPolicy,
    STANDARD_USER_AGENTS
)

logger = logging.getLogger(__name__)

TIKTOK_USER_REGEX = re.compile(r'tiktok\.com/@([a-zA-Z0-9_.-]{2,32})', re.IGNORECASE)
BIO_LINK_REGEX = re.compile(r'https?://[^\s<>"\']+', re.IGNORECASE)


class TikTokDiscoveryConnector(BaseDiscoveryConnector):
    """
    Legitimate free discovery connector for TikTok public content.
    """

    def __init__(self, session=None):
        policy = RateLimitPolicy(
            min_delay_seconds=3.0,
            max_delay_seconds=7.0,
            max_retries=2,
            cooldown_after_rate_limit_seconds=600
        )
        super().__init__(name="tiktok", platform=Platform.TIKTOK, rate_limit_policy=policy, session=session)

    def search_public_profiles(self, query: str) -> List[str]:
        """
        Discovers public TikTok profile usernames via free public search indexing.
        """
        discovered_usernames: Set[str] = set()

        # Method 1: Bing organic search (fast, high yield, datacenter-friendly)
        try:
            bing_results = self.search_bing_organic(f'site:tiktok.com/@ "{query}"', limit=15)
            for item in bing_results:
                full_text = f"{item['url']} {item['snippet']}"
                matches = TIKTOK_USER_REGEX.findall(full_text)
                for u in matches:
                    u_clean = u.strip().lower()
                    if u_clean and u_clean not in ("live", "explore", "foryou", "tag", "login"):
                        discovered_usernames.add(u_clean)
        except Exception as err:
            logger.debug(f"[tiktok] Bing search notice: {err}")

        # Method 2: DuckDuckGo fallback with polite short timeout
        if len(discovered_usernames) < 3 and self.is_healthy():
            ddg_url = "https://html.duckduckgo.com/html/"
            headers = {
                "User-Agent": STANDARD_USER_AGENTS[0],
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
            try:
                resp = self.session.post(ddg_url, data={"q": f'site:tiktok.com/@ "{query}"'}, headers=headers, timeout=3)
                if resp.status_code == 200:
                    matches = TIKTOK_USER_REGEX.findall(resp.text)
                    for u in matches:
                        u_clean = u.strip().lower()
                        if u_clean and u_clean not in ("live", "explore", "foryou", "tag", "login"):
                            discovered_usernames.add(u_clean)
            except Exception:
                pass

        return list(discovered_usernames)

    def inspect_public_profile(self, username: str) -> Tuple[Optional[DiscoveredEntity], List[DiscoveredRelationship], List[DiscoveredEntity]]:
        """
        Inspects a public TikTok profile page to extract bio, metadata, and cross-platform links.
        """
        canonical_id = f"tiktok:{username.lower()}"
        profile_url = f"https://www.tiktok.com/@{username}"
        html = self.fetch_public_url(profile_url)
        if not html:
            # Construct minimal entity from username if page fetch is blocked or requires JS
            entity = DiscoveredEntity(
                platform=Platform.TIKTOK,
                entity_type=EntityType.ACCOUNT,
                canonical_id=canonical_id,
                username=username,
                url=profile_url,
                metadata={"discovery_source": "public_search"}
            )
            return entity, [], []

        soup = BeautifulSoup(html, "html.parser")

        # 1. Title & Meta description
        og_title = soup.find("meta", property="og:title")
        og_desc = soup.find("meta", property="og:description")
        meta_desc = soup.find("meta", attrs={"name": "description"})

        title = og_title.get("content", "").strip() if og_title else username
        description = (og_desc.get("content", "") if og_desc else (meta_desc.get("content", "") if meta_desc else "")).strip()

        # 2. Extract bio links and cross-platform targets
        all_text = f"{title} {description} {html}"
        cross_entities, cross_relations = self.extract_cross_platform_links(
            text=all_text,
            source_canonical_id=canonical_id,
            source_platform=Platform.TIKTOK
        )

        # 3. Evaluate financial relevance
        is_rel, rel_score, matched_kws = evaluate_candidate_relevance(title, description, all_text[:2000])

        main_entity = DiscoveredEntity(
            platform=Platform.TIKTOK,
            entity_type=EntityType.ACCOUNT,
            canonical_id=canonical_id,
            username=username,
            title=title,
            description=description,
            url=profile_url,
            metadata={
                "has_bio": bool(description),
                "bridges_count": len(cross_entities),
                "is_relevant": is_rel,
                "relevance_score": rel_score,
                "matched_terms": matched_kws
            },
            raw_content=description
        )

        return main_entity, cross_relations, cross_entities

    def search(self, query: str, cursor: Optional[str] = None) -> ConnectorSearchResult:
        """
        Executes TikTok discovery for a trading/forex query.
        """
        result = ConnectorSearchResult(query=query, platform=Platform.TIKTOK)
        usernames = self.search_public_profiles(query)

        seen_entities: Set[str] = set()

        for u in usernames[:10]: # Limit per query to respect rate limits
            try:
                main_ent, relations, cross_ents = self.inspect_public_profile(u)
                if main_ent and main_ent.canonical_id not in seen_entities:
                    seen_entities.add(main_ent.canonical_id)
                    result.entities.append(main_ent)

                for cr_ent in cross_ents:
                    if cr_ent.canonical_id not in seen_entities:
                        seen_entities.add(cr_ent.canonical_id)
                        result.entities.append(cr_ent)

                result.relationships.extend(relations)
            except Exception as err:
                logger.debug(f"[tiktok] Error inspecting profile @{u}: {err}")

        self.record_success(len(result.entities))
        return result
