"""
app/discovery/telegram_post_search.py — Telegram Public Channel Post Discovery (channels.searchPosts)

Searches public channel posts by keywords and hashtags (#ذهب, #فوركس, #XAUUSD, #SMC).
Feeds candidates into the shared candidate and validation pipeline with provenance.
"""

import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from tg_manager import TelegramManager
from app.discovery.checkpoint import SearchCheckpointManager
from app.discovery.provenance import ProvenanceManager
from app.discovery.telegram_global_search import TelegramGlobalSearchEngine

logger = logging.getLogger(__name__)


class TelegramPostSearchEngine:
    """
    Executes hashtag and keyword post discovery using native channels.searchPosts
    with graceful fallback and rate handling.
    """

    def __init__(
        self,
        tg_manager: TelegramManager,
        redis_conn,
        db_conn=None,
        candidate_queue: str = "queue:normal"
    ):
        self.tg = tg_manager
        self.redis = redis_conn
        self.db = db_conn
        self.candidate_queue = candidate_queue
        self.checkpoint_mgr = SearchCheckpointManager(redis_conn, db_conn)
        self.provenance_mgr = ProvenanceManager(redis_conn, db_conn)
        self.extractor = TelegramGlobalSearchEngine(tg_manager, redis_conn, db_conn, candidate_queue)

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
        Executes paginated post search for a hashtag with checkpoint resumption.
        """
        shutdown_event = shutdown_event or asyncio.Event()
        search_type = "telegram_search_posts"
        clean_tag = hashtag.lstrip('#')

        # 1. Resume from checkpoint if available
        cp = self.checkpoint_mgr.get_checkpoint(search_type, clean_tag)
        offset_id = cp.get("offset_id", 0) if cp else 0
        offset_rate = cp.get("offset_rate", 0) if cp else 0
        page = cp.get("page_number", 1) if cp else 1
        total_discovered = cp.get("total_yield", 0) if cp else 0

        pages_executed = 0
        new_channels_found = 0

        while pages_executed < max_pages and not shutdown_event.is_set():
            logger.info(f"[SearchPosts] Hashtag #{clean_tag} — Fetching page {page} (offset_id={offset_id})...")
            try:
                res = await self.tg.search_posts(
                    hashtag=clean_tag,
                    offset_rate=offset_rate,
                    offset_id=offset_id,
                    limit=limit_per_page,
                    shutdown_event=shutdown_event
                )
            except Exception as err:
                logger.warning(f"[SearchPosts] Hashtag #{clean_tag} page {page} failed: {err}")
                break

            if not res or not getattr(res, 'messages', []):
                logger.info(f"[SearchPosts] Hashtag #{clean_tag} reached end of results.")
                self.checkpoint_mgr.save_checkpoint(
                    search_type=search_type,
                    query_key=clean_tag,
                    offset_id=0,
                    offset_rate=0,
                    page_number=page,
                    total_yield=total_discovered,
                    status="completed"
                )
                break

            candidates = self.extractor.extract_channel_candidates(res, f"#{clean_tag}")
            for cand in candidates:
                raw_handle = cand["username"] or f"https://t.me/c/{cand['channel_id']}/1"
                is_new, count, sources = self.provenance_mgr.record_candidate_discovery(
                    username_or_link=raw_handle,
                    source_type=search_type,
                    keyword=f"#{clean_tag}",
                    metadata={
                        "channel_id": cand["channel_id"],
                        "title": cand["title"],
                        "matched_message_id": cand["matched_message_id"],
                        "post_preview": cand["post_text_preview"]
                    }
                )

                if is_new:
                    # Enqueue for Stage 1 cheap validation
                    self.redis.rpush(self.candidate_queue, cand["username"] or cand["handle_or_link"])
                    new_channels_found += 1
                    total_discovered += 1

            # Update pagination offsets
            msgs = res.messages
            last_msg = msgs[-1]
            offset_id = getattr(last_msg, 'id', 0)
            offset_rate = getattr(res, 'next_rate', 0) if hasattr(res, 'next_rate') else 0
            page += 1
            pages_executed += 1

            self.checkpoint_mgr.save_checkpoint(
                search_type=search_type,
                query_key=clean_tag,
                offset_id=offset_id,
                offset_rate=offset_rate,
                page_number=page,
                total_yield=total_discovered,
                status="in_progress"
            )

            # Polite throttle between search pages
            await asyncio.sleep(2.0)

        return {
            "hashtag": clean_tag,
            "pages_executed": pages_executed,
            "new_channels_found": new_channels_found,
            "total_yield": total_discovered
        }
