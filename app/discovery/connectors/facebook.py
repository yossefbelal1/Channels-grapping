"""
app/discovery/connectors/facebook.py — Free Public Facebook Discovery Connector

Discovers public Facebook Pages, trading groups, and profiles related to Forex/Gold trading
using legitimate free public search indexing and public page metadata parsing.
Extracts cross-platform bridges (Facebook -> Telegram, Facebook -> TikTok, Facebook -> Website).
"""

import re
import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from bs4 import BeautifulSoup

from app.discovery.entity_model import (
    Platform, EntityType, RelationType, CanonicalIdentity,
    DiscoveredEntity, DiscoveredRelationship, evaluate_candidate_relevance
)
from app.discovery.connectors.base import (
    BaseDiscoveryConnector, ConnectorSearchResult, RateLimitPolicy,
    STANDARD_USER_AGENTS, FACEBOOK_LINK_REGEX
)

logger = logging.getLogger(__name__)


class FacebookDiscoveryConnector(BaseDiscoveryConnector):
    """
    Legitimate free discovery connector for Facebook public pages and trading communities.
    """

    def __init__(self, session=None):
        policy = RateLimitPolicy(
            min_delay_seconds=3.0,
            max_delay_seconds=7.0,
            max_retries=2,
            cooldown_after_rate_limit_seconds=600
        )
        super().__init__(name="facebook", platform=Platform.FACEBOOK, rate_limit_policy=policy, session=session)

    def search_public_pages(self, query: str) -> List[str]:
        """
        Discovers public Facebook page slugs/URLs via free public search indexing.
        """
        discovered_slugs: Set[str] = set()

        # Method 1: Bing organic search (fast, high yield, datacenter-friendly)
        try:
            bing_results = self.search_bing_organic(f'site:facebook.com "{query}" (t.me OR telegram)', limit=15)
            for item in bing_results:
                full_text = f"{item['url']} {item['snippet']}"
                matches = FACEBOOK_LINK_REGEX.findall(full_text)
                for slug in matches:
                    s_clean = slug.strip().lower()
                    if s_clean and s_clean not in (
                        "pages", "groups", "share", "watch", "login", "home", "help",
                        "policies", "privacy", "terms", "marketplace", "recover"
                    ):
                        discovered_slugs.add(s_clean)
        except Exception as err:
            logger.debug(f"[facebook] Bing search notice: {err}")

        # Method 2: DuckDuckGo fallback with short polite timeout
        if len(discovered_slugs) < 3 and self.is_healthy():
            ddg_url = "https://html.duckduckgo.com/html/"
            headers = {
                "User-Agent": STANDARD_USER_AGENTS[1],
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
            try:
                resp = self.session.post(ddg_url, data={"q": f'site:facebook.com "{query}" (t.me OR telegram)'}, headers=headers, timeout=3)
                if resp.status_code == 200:
                    matches = FACEBOOK_LINK_REGEX.findall(resp.text)
                    for slug in matches:
                        s_clean = slug.strip().lower()
                        if s_clean and s_clean not in ("pages", "groups", "share", "watch", "login", "help"):
                            discovered_slugs.add(s_clean)
            except Exception:
                pass

        return list(discovered_slugs)

    def inspect_public_page(self, slug: str) -> Tuple[Optional[DiscoveredEntity], List[DiscoveredRelationship], List[DiscoveredEntity]]:
        """
        Inspects public Facebook page HTML metadata to extract title, description, and bridges.
        """
        canonical_id = f"facebook:{slug.lower()}"
        page_url = f"https://www.facebook.com/{slug}"
        html = self.fetch_public_url(page_url)

        if not html:
            entity = DiscoveredEntity(
                platform=Platform.FACEBOOK,
                entity_type=EntityType.PAGE,
                canonical_id=canonical_id,
                username=slug,
                url=page_url,
                metadata={"discovery_source": "public_search"}
            )
            return entity, [], []

        soup = BeautifulSoup(html, "html.parser")

        og_title = soup.find("meta", property="og:title")
        og_desc = soup.find("meta", property="og:description")
        meta_desc = soup.find("meta", attrs={"name": "description"})

        title = og_title.get("content", "").strip() if og_title else slug
        description = (og_desc.get("content", "") if og_desc else (meta_desc.get("content", "") if meta_desc else "")).strip()

        all_text = f"{title} {description} {html}"
        cross_entities, cross_relations = self.extract_cross_platform_links(
            text=all_text,
            source_canonical_id=canonical_id,
            source_platform=Platform.FACEBOOK
        )

        # Evaluate financial relevance
        is_rel, rel_score, matched_kws = evaluate_candidate_relevance(title, description, all_text[:2000])

        main_entity = DiscoveredEntity(
            platform=Platform.FACEBOOK,
            entity_type=EntityType.PAGE,
            canonical_id=canonical_id,
            username=slug,
            title=title,
            description=description,
            url=page_url,
            metadata={
                "has_description": bool(description),
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
        Executes Facebook discovery for a trading/forex query.
        """
        result = ConnectorSearchResult(query=query, platform=Platform.FACEBOOK)
        slugs = self.search_public_pages(query)

        seen_entities: Set[str] = set()

        for slug in slugs[:10]:
            try:
                main_ent, relations, cross_ents = self.inspect_public_page(slug)
                if main_ent and main_ent.canonical_id not in seen_entities:
                    seen_entities.add(main_ent.canonical_id)
                    result.entities.append(main_ent)

                for cr_ent in cross_ents:
                    if cr_ent.canonical_id not in seen_entities:
                        seen_entities.add(cr_ent.canonical_id)
                        result.entities.append(cr_ent)

                result.relationships.extend(relations)
            except Exception as err:
                logger.debug(f"[facebook] Error inspecting page {slug}: {err}")

        self.record_success(len(result.entities))
        return result
