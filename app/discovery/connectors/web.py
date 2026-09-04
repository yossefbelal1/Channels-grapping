"""
app/discovery/connectors/web.py — Free Web & Directory Discovery Connector

Discovers trading blogs, signal providers, broker portals, directories, and cross-platform
communities using multi-provider free public search engines and direct website crawling.
"""

import re
import urllib.parse
import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from bs4 import BeautifulSoup

from app.discovery.entity_model import (
    Platform, EntityType, RelationType, CanonicalIdentity,
    DiscoveredEntity, DiscoveredRelationship
)
from app.discovery.connectors.base import (
    BaseDiscoveryConnector, ConnectorSearchResult, RateLimitPolicy,
    STANDARD_USER_AGENTS, TELEGRAM_LINK_REGEX, TIKTOK_LINK_REGEX,
    FACEBOOK_LINK_REGEX, WEB_URL_REGEX
)

logger = logging.getLogger(__name__)


class WebDiscoveryConnector(BaseDiscoveryConnector):
    """
    Legitimate free discovery connector for trading websites, financial directories, and blogs.
    """

    DIRECTORY_TARGETS = [
        "https://telegramchannels.me/search?query={query}",
        "https://tlgrm.eu/channels?search={query}"
    ]

    def __init__(self, session=None):
        policy = RateLimitPolicy(
            min_delay_seconds=2.5,
            max_delay_seconds=6.0,
            max_retries=2,
            cooldown_after_rate_limit_seconds=300
        )
        super().__init__(name="web", platform=Platform.WEB, rate_limit_policy=policy, session=session)

    def search_directories(self, query: str) -> List[str]:
        """Scrapes free channel directories with fast timeouts."""
        discovered_links: Set[str] = set()
        headers = {"User-Agent": STANDARD_USER_AGENTS[2]}

        for template in self.DIRECTORY_TARGETS:
            try:
                url = template.format(query=urllib.parse.quote_plus(query))
                resp = self.session.get(url, headers=headers, timeout=3)
                if resp.status_code == 200:
                    matches = TELEGRAM_LINK_REGEX.findall(resp.text)
                    for m in matches:
                        clean_u = m.strip().lstrip('@').lower()
                        if clean_u and not clean_u.endswith("bot") and clean_u not in ("joinchat", "share", "addlist", "username", "contact"):
                            discovered_links.add(f"https://t.me/{clean_u}")
            except Exception as err:
                logger.debug(f"[web] Directory search error ({template}): {err}")

        return list(discovered_links)

    def search_search_engines(self, query: str) -> Tuple[List[str], List[str]]:
        """
        Executes public search engine queries to find both direct Telegram channels
        and external trading websites. Uses Bing organic as fast, reliable primary.
        """
        tg_links: Set[str] = set()
        websites: Set[str] = set()

        # 1. Primary: Bing Organic Search
        try:
            bing_results = self.search_bing_organic(f'"{query}" (site:t.me OR "t.me/")', limit=15)
            for item in bing_results:
                full_text = f"{item['title']} {item['url']} {item['snippet']}"
                for m in TELEGRAM_LINK_REGEX.findall(full_text):
                    clean_u = m.strip().lstrip('@').lower()
                    if clean_u and not clean_u.endswith("bot") and clean_u not in ("joinchat", "share", "username", "contact"):
                        tg_links.add(f"https://t.me/{clean_u}")

                # Also capture external websites for bridge crawling
                u = item['url']
                parsed = urllib.parse.urlparse(u)
                if parsed.netloc and not any(k in parsed.netloc for k in ["t.me", "telegram.me", "bing.com", "microsoft.com", "google.com"]):
                    websites.add(f"{parsed.scheme}://{parsed.netloc}")
        except Exception as err:
            logger.debug(f"[web] Bing search engine notice: {err}")

        # 2. Secondary fallback: DuckDuckGo with fast timeout
        if len(tg_links) < 2:
            ddg_url = "https://html.duckduckgo.com/html/"
            headers = {
                "User-Agent": STANDARD_USER_AGENTS[0],
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
            try:
                resp = self.session.post(ddg_url, data={"q": f'"{query}" (site:t.me OR "t.me/")'}, headers=headers, timeout=3)
                if resp.status_code == 200:
                    for m in TELEGRAM_LINK_REGEX.findall(resp.text):
                        clean_u = m.strip().lstrip('@').lower()
                        if clean_u and not clean_u.endswith("bot") and clean_u not in ("joinchat", "share", "username", "contact"):
                            tg_links.add(f"https://t.me/{clean_u}")
            except Exception:
                pass

        return list(tg_links), list(websites)

    def crawl_website_for_bridges(self, website_url: str) -> Tuple[Optional[DiscoveredEntity], List[DiscoveredRelationship], List[DiscoveredEntity]]:
        """
        Crawls a financial/trading website to discover embedded social profiles and channels.
        """
        parsed = urllib.parse.urlparse(website_url)
        domain = parsed.netloc.lower().lstrip("www.")
        canonical_id = f"web:{domain}"

        html = self.fetch_public_url(website_url, timeout=10)
        if not html:
            entity = DiscoveredEntity(
                platform=Platform.WEB,
                entity_type=EntityType.WEBSITE,
                canonical_id=canonical_id,
                url=website_url,
                metadata={"domain": domain}
            )
            return entity, [], []

        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else domain

        meta_desc = soup.find("meta", attrs={"name": "description"})
        og_desc = soup.find("meta", property="og:description")
        description = (og_desc.get("content", "") if og_desc else (meta_desc.get("content", "") if meta_desc else "")).strip()

        # Extract all cross-platform links on the website
        all_text = f"{title} {description} {html}"
        cross_entities, cross_relations = self.extract_cross_platform_links(
            text=all_text,
            source_canonical_id=canonical_id,
            source_platform=Platform.WEB
        )

        main_entity = DiscoveredEntity(
            platform=Platform.WEB,
            entity_type=EntityType.WEBSITE,
            canonical_id=canonical_id,
            title=title,
            description=description,
            url=website_url,
            metadata={
                "domain": domain,
                "social_bridges_count": len(cross_entities)
            },
            raw_content=description
        )

        return main_entity, cross_relations, cross_entities

    def search(self, query: str, cursor: Optional[str] = None) -> ConnectorSearchResult:
        """
        Runs comprehensive web discovery across directories, search engines, and website crawling.
        """
        result = ConnectorSearchResult(query=query, platform=Platform.WEB)
        seen_canonical: Set[str] = set()

        # 1. Directory search
        dir_links = self.search_directories(query)
        for link in dir_links:
            u = link.replace("https://t.me/", "").strip().lower()
            can_id = f"telegram:{u}"
            if can_id not in seen_canonical:
                seen_canonical.add(can_id)
                ent = DiscoveredEntity(
                    platform=Platform.TELEGRAM,
                    entity_type=EntityType.CHANNEL,
                    canonical_id=can_id,
                    username=u,
                    url=link,
                    metadata={"source": "directory", "query": query}
                )
                result.entities.append(ent)

        # 2. Search engine queries
        tg_search_links, websites = self.search_search_engines(query)
        for link in tg_search_links:
            u = link.replace("https://t.me/", "").strip().lower()
            can_id = f"telegram:{u}"
            if can_id not in seen_canonical:
                seen_canonical.add(can_id)
                ent = DiscoveredEntity(
                    platform=Platform.TELEGRAM,
                    entity_type=EntityType.CHANNEL,
                    canonical_id=can_id,
                    username=u,
                    url=link,
                    metadata={"source": "web_search", "query": query}
                )
                result.entities.append(ent)

        # 3. Direct website crawling for social bridges
        for site in websites[:5]:
            try:
                site_ent, relations, bridges = self.crawl_website_for_bridges(site)
                if site_ent and site_ent.canonical_id not in seen_canonical:
                    seen_canonical.add(site_ent.canonical_id)
                    result.entities.append(site_ent)

                for b in bridges:
                    if b.canonical_id not in seen_canonical:
                        seen_canonical.add(b.canonical_id)
                        result.entities.append(b)

                result.relationships.extend(relations)
            except Exception as err:
                logger.debug(f"[web] Error crawling website {site}: {err}")

        self.record_success(len(result.entities))
        return result
