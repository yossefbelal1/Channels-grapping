"""
app/discovery/telegram_post_search.py — Telegram Public Channel Post Discovery (channels.searchPosts)

Searches public channel posts by both hashtags (#ذهب, #فوركس, #XAUUSD, #SMC)
and normal text queries ("Forex signals", "توصيات فوركس").
Maintains complete pagination offsets (offset_id, offset_rate, offset_peer).
Provides clean, unnested fallback to TelegramGlobalSearchEngine upon API restriction.
"""

import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from tg_manager import TelegramManager, SearchPostsUnsupportedError
from app.discovery.checkpoint import SearchCheckpointManager
from app.discovery.provenance import ProvenanceManager
from app.discovery.telegram_global_search import TelegramGlobalSearchEngine

logger = logging.getLogger(__name__)


class TelegramPostSearchEngine:
    """
    Executes hashtag and text post discovery using native channels.searchPosts
    with stateful pagination and clean fallback handling.
    """

    def __init__(
        self,
        tg_manager: TelegramManager,
        redis_conn,
        db_conn=None,
        candidate_queue: str = "queue:normal",
        global_search_engine: Optional[TelegramGlobalSearchEngine] = None
    ):
        self.tg = tg_manager
        self.redis = redis_conn
        self.db = db_conn
        self.candidate_queue = candidate_queue
        self.checkpoint_mgr = SearchCheckpointManager(redis_conn, db_conn)
        self.provenance_mgr = ProvenanceManager(redis_conn, db_conn)
        self.global_search_engine = global_search_engine or TelegramGlobalSearchEngine(
            tg_manager, redis_conn, db_conn, candidate_queue
        )

    def get_target_hashtags(self) -> List[str]:
        """
        Returns high-yield trading hashtags in Arabic and English.
        """
        return [
            "فوركس", "ذهب", "تداول", "توصيات", "تحليل_فني", "سكالبينج",
            "XAUUSD", "forex", "gold", "trading", "signals", "SMC", "ICT",
            "EURUSD", "GBPUSD", "forexsignals", "scalping"
        ]

    async def search_hashtag_paginated(
        self,
        hashtag: str,
        max_pages: int = 3,
        limit_per_page: int = 50,
        shutdown_event: Optional[asyncio.Event] = None
    ) -> Dict[str, Any]:
        """
        Executes paginated post search for a hashtag with complete offset checkpointing.
        """
        return await self._execute_search_paginated(
            hashtag=hashtag,
            query=None,
            max_pages=max_pages,
            limit_per_page=limit_per_page,
            shutdown_event=shutdown_event
        )

    async def search_query_paginated(
        self,
        query: str,
        max_pages: int = 3,
        limit_per_page: int = 50,
        shutdown_event: Optional[asyncio.Event] = None
    ) -> Dict[str, Any]:
        """
        Executes paginated post search for a normal text query.
        """
        return await self._execute_search_paginated(
            hashtag=None,
            query=query,
            max_pages=max_pages,
            limit_per_page=limit_per_page,
            shutdown_event=shutdown_event
        )

    async def _execute_search_paginated(
        self,
        hashtag: Optional[str] = None,
        query: Optional[str] = None,
        max_pages: int = 3,
        limit_per_page: int = 50,
        shutdown_event: Optional[asyncio.Event] = None
    ) -> Dict[str, Any]:
        shutdown_event = shutdown_event or asyncio.Event()
        search_type = "telegram_search_posts"
        clean_tag = hashtag.lstrip('#') if hashtag else None
        query_key = f"tag_{clean_tag}" if clean_tag else f"query_{query.strip().lower()}"
        matched_label = f"#{clean_tag}" if clean_tag else query

        # 1. Resume from checkpoint if available
        cp = self.checkpoint_mgr.get_checkpoint(search_type, query_key)
        offset_id = cp.get("offset_id", 0) if cp else 0
        offset_rate = cp.get("offset_rate", 0) if cp else 0
        offset_peer_id = cp.get("offset_peer_id", None) if cp else None
        page = cp.get("page_number", 1) if cp else 1
        total_discovered = cp.get("total_yield", 0) if cp else 0

        pages_executed = 0
        new_channels_found = 0
        prev_state = None

        while pages_executed < max_pages and not shutdown_event.is_set():
            logger.info(
                f"[SearchPosts] Searching '{matched_label}' — Page {page} "
                f"(offset_id={offset_id}, offset_rate={offset_rate}, offset_peer={offset_peer_id})..."
            )
            try:
                res = await self.tg.search_posts(
                    query=query,
                    hashtag=clean_tag,
                    offset_peer=offset_peer_id,
                    offset_rate=offset_rate,
                    offset_id=offset_id,
                    limit=limit_per_page,
                    shutdown_event=shutdown_event
                )
            except SearchPostsUnsupportedError as err:
                logger.info(
                    f"[SearchPosts] channels.searchPosts unsupported or restricted: {err}. "
                    f"Activating clean global message search fallback for '{matched_label}'."
                )
                # Clean fallback without recursive retry loops
                return await self.global_search_engine.search_query_paginated(
                    query=matched_label,
                    max_pages=max_pages,
                    limit_per_page=limit_per_page,
                    shutdown_event=shutdown_event
                )
            except Exception as err:
                logger.warning(f"[SearchPosts] Search '{matched_label}' page {page} failed: {err}")
                break

            if not res or not getattr(res, 'messages', []):
                logger.info(f"[SearchPosts] Search '{matched_label}' reached end of results.")
                self.checkpoint_mgr.save_checkpoint(
                    search_type=search_type,
                    query_key=query_key,
                    offset_id=0,
                    offset_rate=0,
                    offset_peer_id=None,
                    offset_peer_type=None,
                    page_number=page,
                    total_yield=total_discovered,
                    status="completed"
                )
                break

            candidates = self.global_search_engine.extract_channel_candidates(res, matched_label)
            for cand in candidates:
                raw_handle = cand["username"] or f"https://t.me/c/{cand['channel_id']}/1"
                is_new, count, sources = self.provenance_mgr.record_candidate_discovery(
                    username_or_link=raw_handle,
                    source_type=search_type,
                    keyword=matched_label,
                    metadata={
                        "channel_id": cand["channel_id"],
                        "title": cand["title"],
                        "matched_message_id": cand["matched_message_id"],
                        "post_preview": cand["post_text_preview"]
                    }
                )

                if is_new:
                    self.redis.rpush(self.candidate_queue, cand["username"] or cand["handle_or_link"])
                    new_channels_found += 1
                    total_discovered += 1

            # Extract next pagination state
            msgs = res.messages
            last_msg = msgs[-1]
            next_offset_id = getattr(last_msg, 'id', 0)
            next_offset_rate = getattr(res, 'next_rate', 0) if hasattr(res, 'next_rate') else 0

            next_peer_id = None
            next_peer_type = None
            peer_obj = getattr(last_msg, 'peer_id', None)
            if peer_obj:
                if hasattr(peer_obj, 'channel_id'):
                    next_peer_id = peer_obj.channel_id
                    next_peer_type = "channel"
                elif hasattr(peer_obj, 'chat_id'):
                    next_peer_id = peer_obj.chat_id
                    next_peer_type = "chat"
                elif hasattr(peer_obj, 'user_id'):
                    next_peer_id = peer_obj.user_id
                    next_peer_type = "user"

            current_state = (next_offset_id, next_offset_rate, next_peer_id)
            if current_state == prev_state:
                logger.info(f"[SearchPosts] Search '{matched_label}' returned duplicate offset state. Ending pagination.")
                break
            prev_state = current_state

            offset_id = next_offset_id
            offset_rate = next_offset_rate
            offset_peer_id = next_peer_id
            page += 1
            pages_executed += 1

            self.checkpoint_mgr.save_checkpoint(
                search_type=search_type,
                query_key=query_key,
                offset_id=offset_id,
                offset_rate=offset_rate,
                offset_peer_id=offset_peer_id,
                offset_peer_type=next_peer_type,
                page_number=page,
                total_yield=total_discovered,
                status="in_progress"
            )

            await asyncio.sleep(1.5)

        return {
            "search_term": matched_label,
            "pages_executed": pages_executed,
            "new_channels_found": new_channels_found,
            "total_yield": total_discovered,
            "last_offset_id": offset_id,
            "last_offset_rate": offset_rate,
            "last_offset_peer_id": offset_peer_id
        }
