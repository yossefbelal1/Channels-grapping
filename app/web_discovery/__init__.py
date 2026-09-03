"""
app.web_discovery — Pluggable External Web & Directory Discovery Package
"""

from app.web_discovery.engines import (
    WebDiscoveryEngine,
    GoogleSearchProvider,
    BingSearchProvider,
    TelegramDirectoryProvider,
    extract_telegram_links_from_html
)

__all__ = [
    "WebDiscoveryEngine",
    "GoogleSearchProvider",
    "BingSearchProvider",
    "TelegramDirectoryProvider",
    "extract_telegram_links_from_html"
]
