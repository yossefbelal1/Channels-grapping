"""
app/discovery/connectors/telegram.py — Unified Telegram Discovery Connector

Integrates existing Telegram global search, post search, and post content extraction
under the BaseDiscoveryConnector interface. Automatically extracts cross-platform
bridges from Telegram channel bios and post texts (Telegram -> TikTok, Facebook, Web).
"""

import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from app.discovery.entity_model import (
    Platform, EntityType, RelationType, CanonicalIdentity,
    DiscoveredEntity, DiscoveredRelationship
)
from app.discovery.connectors.base import BaseDiscoveryConnector, ConnectorSearchResult, RateLimitPolicy

logger = logging.getLogger(__name__)


class TelegramDiscoveryConnector(BaseDiscoveryConnector):
    """
    Unified Telegram connector managing Telegram-native channel discovery
    and outbound cross-platform link extraction.
    """

    def __init__(self, tg_manager=None, session=None):
        policy = RateLimitPolicy(
            min_delay_seconds=2.0,
            max_delay_seconds=5.0,
            max_retries=3,
            cooldown_after_rate_limit_seconds=180
        )
        super().__init__(name="telegram", platform=Platform.TELEGRAM, rate_limit_policy=policy, session=session)
        self.tg_manager = tg_manager

    def search(self, query: str, cursor: Optional[str] = None) -> ConnectorSearchResult:
        """
        Executes search. In pure connector mode, extracts channel candidates
        from public Telegram directory or telethon client if available.
        """
        result = ConnectorSearchResult(query=query, platform=Platform.TELEGRAM)
        # Note: when running within the worker, Telethon global search calls are coordinated
        # via the worker's telegram manager. This search method provides the normalized bridge.
        return result

    def inspect_channel_content_for_bridges(
        self,
        channel_username: str,
        description: str,
        recent_posts: Optional[List[str]] = None
    ) -> Tuple[DiscoveredEntity, List[DiscoveredRelationship], List[DiscoveredEntity]]:
        """
        Extracts outbound social and website bridges from a Telegram channel's
        bio description and recent broadcast messages.
        """
        clean_username = channel_username.strip().lstrip('@').lower()
        canonical_id = f"telegram:{clean_username}"

        main_entity = DiscoveredEntity(
            platform=Platform.TELEGRAM,
            entity_type=EntityType.CHANNEL,
            canonical_id=canonical_id,
            username=clean_username,
            description=description,
            url=f"https://t.me/{clean_username}"
        )

        combined_text = f"{description} " + " ".join(recent_posts or [])
        cross_entities, cross_relations = self.extract_cross_platform_links(
            text=combined_text,
            source_canonical_id=canonical_id,
            source_platform=Platform.TELEGRAM
        )

        return main_entity, cross_relations, cross_entities
