"""
app/discovery/connectors/__init__.py — Unified Discovery Connectors Package
"""

from app.discovery.connectors.base import (
    BaseDiscoveryConnector,
    RateLimitPolicy,
    ConnectorHealth,
    ConnectorSearchResult,
    TELEGRAM_LINK_REGEX,
    TIKTOK_LINK_REGEX,
    FACEBOOK_LINK_REGEX,
    WHATSAPP_LINK_REGEX,
    WEB_URL_REGEX
)
from app.discovery.connectors.tiktok import TikTokDiscoveryConnector
from app.discovery.connectors.facebook import FacebookDiscoveryConnector
from app.discovery.connectors.web import WebDiscoveryConnector
from app.discovery.connectors.telegram import TelegramDiscoveryConnector

__all__ = [
    "BaseDiscoveryConnector",
    "RateLimitPolicy",
    "ConnectorHealth",
    "ConnectorSearchResult",
    "TikTokDiscoveryConnector",
    "FacebookDiscoveryConnector",
    "WebDiscoveryConnector",
    "TelegramDiscoveryConnector",
    "TELEGRAM_LINK_REGEX",
    "TIKTOK_LINK_REGEX",
    "FACEBOOK_LINK_REGEX",
    "WHATSAPP_LINK_REGEX",
    "WEB_URL_REGEX"
]
