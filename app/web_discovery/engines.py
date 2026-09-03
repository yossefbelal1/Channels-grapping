"""
app/web_discovery/engines.py — Pluggable Web & Directory Discovery Engines
"""

import re
import logging
import random
from typing import List, Set, Optional
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

TELEGRAM_LINK_REGEX = re.compile(
    r'(?:https?://)?(?:t\.me|telegram\.me)/(?:joinchat/)?\+?[a-zA-Z0-9_.-]+',
    re.IGNORECASE
)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]


def extract_telegram_links_from_html(html: str) -> List[str]:
    """Extracts and normalizes all public Telegram links from an HTML document or raw text."""
    if not html:
        return []

    found = TELEGRAM_LINK_REGEX.findall(html)
    results: List[str] = []
    seen: Set[str] = set()

    for link in found:
        clean = link.strip()
        if not clean.startswith("http"):
            clean = f"https://{clean}"
        clean_norm = clean.lower()
        if clean_norm not in seen and not clean_norm.endswith("bot") and not clean_norm.endswith("_bot"):
            seen.add(clean_norm)
            results.append(clean)

    return results


class WebSearchProvider:
    """Base class for pluggable web discovery providers."""
    name: str = "base"

    def search(self, query: str, session: requests.Session) -> List[str]:
        raise NotImplementedError


class GoogleSearchProvider(WebSearchProvider):
    name = "google"

    def search(self, query: str, session: requests.Session) -> List[str]:
        url = "https://html.duckduckgo.com/html/"
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        try:
            resp = session.post(url, data={"q": f"{query} site:t.me"}, headers=headers, timeout=12)
            if resp.status_code == 200:
                return extract_telegram_links_from_html(resp.text)
        except Exception as err:
            logger.debug(f"DuckDuckGo search error for '{query}': {err}")
        return []


class BingSearchProvider(WebSearchProvider):
    name = "bing"

    def search(self, query: str, session: requests.Session) -> List[str]:
        url = f"https://www.bing.com/search?q={query}+site%3At.me"
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        try:
            resp = session.get(url, headers=headers, timeout=12)
            if resp.status_code == 200:
                return extract_telegram_links_from_html(resp.text)
        except Exception as err:
            logger.debug(f"Bing search error for '{query}': {err}")
        return []


class TelegramDirectoryProvider(WebSearchProvider):
    name = "directory"

    def search(self, query: str, session: requests.Session) -> List[str]:
        # Scrapes directory catalog search endpoints
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        links = []
        try:
            # Arabic Telegram channels directory
            target_url = f"https://telegramchannels.me/search?query={query}"
            resp = session.get(target_url, headers=headers, timeout=10)
            if resp.status_code == 200:
                links.extend(extract_telegram_links_from_html(resp.text))
        except Exception as err:
            logger.debug(f"Directory search error for '{query}': {err}")
        return links


class WebDiscoveryEngine:
    """
    Coordinates multi-provider web scraping to discover Telegram channels from public internet.
    """

    def __init__(self, providers: Optional[List[WebSearchProvider]] = None):
        self.providers = providers or [
            GoogleSearchProvider(),
            BingSearchProvider(),
            TelegramDirectoryProvider()
        ]
        self.session = requests.Session()

    def discover_channels_for_query(self, query: str) -> List[str]:
        """Runs query across all providers and aggregates discovered Telegram links."""
        discovered: Set[str] = set()
        for provider in self.providers:
            try:
                results = provider.search(query, self.session)
                for link in results:
                    discovered.add(link)
            except Exception as err:
                logger.warning(f"Web discovery provider {provider.name} failed on '{query}': {err}")

        return list(discovered)
