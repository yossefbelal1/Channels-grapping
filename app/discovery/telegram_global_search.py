"""
app/discovery/telegram_global_search.py — Telegram Global Message Discovery Engine

Implements native messages.searchGlobal discovery across public Telegram channels.
Discovers channels based on post content signals (e.g. XAUUSD trade setups)
even when channel titles lack Forex keywords.
Maintains full pagination state (offset_id, offset_rate, offset_peer, page_number).
"""

import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple

from tg_manager import TelegramManager
from app.discovery.checkpoint import SearchCheckpointManager
from app.discovery.provenance import ProvenanceManager
from app.discovery.taxonomy import get_all_keywords, get_category_keywords
from app.discovery.arabic_normalizer import generate_query_variants

logger = logging.getLogger(__name__)


class TelegramGlobalSearchEngine:
    """
    Executes content-based global message search with stateful pagination,
    provenance tracking, deduplication, and candidate queueing.
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

    def get_search_queries(self) -> List[str]:
        """
        Gathers high-priority search queries across Arabic & English Forex taxonomy.
        """
        queries = []
        for cat in ["FOREX", "GOLD_XAUUSD", "SIGNALS", "SMC_ICT", "TRADING_STYLES"]:
            for kw in get_category_keywords(cat):
                queries.append(kw)
                for var in generate_query_variants(kw):
                    if var not in queries:
                        queries.append(var)
        return queries[:150]

    def extract_channel_candidates(self, search_result, matched_query: str) -> List[Dict[str, Any]]:
        """
        Parses Telethon messages.searchGlobal or channels.searchPosts response.
        Extracts channel ID, username, title, message ID, date, and matched query.
        """
        if not search_result:
            return []

        candidates = []
        chats_map = {}
        for chat in getattr(search_result, 'chats', []):
            cid = getattr(chat, 'id', None)
            if cid:
                chats_map[cid] = chat

        messages = getattr(search_result, 'messages', [])
        for msg in messages:
            chat_obj = None
            peer_id = getattr(msg, 'peer_id', None)
            if peer_id:
                chan_id = getattr(peer_id, 'channel_id', None)
                if chan_id and chan_id in chats_map:
                    chat_obj = chats_map[chan_id]

            if not chat_obj:
                chat_obj = getattr(msg, 'chat', None)

            if chat_obj and getattr(chat_obj, 'broadcast', True):
                username = getattr(chat_obj, 'username', None)
                title = getattr(chat_obj, 'title', "")
                channel_id = str(getattr(chat_obj, 'id', ""))
                msg_id = getattr(msg, 'id', None)
                msg_date = getattr(msg, 'date', None)

                handle_or_link = username or f"channel_{channel_id}"
                if handle_or_link:
                    candidates.append({
                        "channel_id": channel_id,
                        "username": username,
                        "title": title,
                        "handle_or_link": handle_or_link,
                        "matched_message_id": msg_id,
                        "message_date": msg_date.isoformat() if isinstance(msg_date, datetime) else str(msg_date),
                        "matched_query": matched_query,
                        "post_text_preview": (getattr(msg, 'text', '') or '')[:200]
                    })

        return candidates

    async def search_query_paginated(
        self,
        query: str,
        max_pages: int = 5,
        limit_per_page: int = 50,
        shutdown_event: Optional[asyncio.Event] = None
    ) -> Dict[str, Any]:
        """
        Executes paginated global search for a query with full offset checkpoint resumption.
        Feeds newly discovered candidates directly into the candidate queue.
        """
        shutdown_event = shutdown_event or asyncio.Event()
        search_type = "telegram_global_search"

        # 1. Resume from checkpoint if available
        cp = self.checkpoint_mgr.get_checkpoint(search_type, query)
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
                f"[GlobalSearch] Query '{query}' — Fetching page {page} "
                f"(offset_id={offset_id}, offset_rate={offset_rate}, offset_peer={offset_peer_id})..."
            )
            try:
                res = await self.tg.search_global_messages(
                    query=query,
                    offset_peer=offset_peer_id,
                    offset_rate=offset_rate,
                    offset_id=offset_id,
                    limit=limit_per_page,
                    shutdown_event=shutdown_event
                )
            except Exception as err:
                logger.warning(f"[GlobalSearch] Query '{query}' page {page} failed: {err}")
                break

            if not res or not getattr(res, 'messages', []):
                logger.info(f"[GlobalSearch] Query '{query}' reached end of results.")
                self.checkpoint_mgr.save_checkpoint(
                    search_type=search_type,
                    query_key=query,
                    offset_id=0,
                    offset_rate=0,
                    offset_peer_id=None,
                    offset_peer_type=None,
                    page_number=page,
                    total_yield=total_discovered,
                    status="completed"
                )
                break

            candidates = self.extract_channel_candidates(res, query)
            for cand in candidates:
                raw_handle = cand["username"] or f"https://t.me/c/{cand['channel_id']}/1"
                is_new, count, sources = self.provenance_mgr.record_candidate_discovery(
                    username_or_link=raw_handle,
                    source_type=search_type,
                    keyword=query,
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
            
            # Extract peer ID
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

            # Check for duplicate page loops
            current_state = (next_offset_id, next_offset_rate, next_peer_id)
            if current_state == prev_state:
                logger.info(f"[GlobalSearch] Query '{query}' returned identical offset state. Ending pagination.")
                break
            prev_state = current_state

            offset_id = next_offset_id
            offset_rate = next_offset_rate
            offset_peer_id = next_peer_id
            page += 1
            pages_executed += 1

            self.checkpoint_mgr.save_checkpoint(
                search_type=search_type,
                query_key=query,
                offset_id=offset_id,
                offset_rate=offset_rate,
                offset_peer_id=offset_peer_id,
                offset_peer_type=next_peer_type,
                page_number=page,
                total_yield=total_discovered,
                status="in_progress"
            )

            # Polite throttle between search pages
            await asyncio.sleep(1.5)

        return {
            "query": query,
            "pages_executed": pages_executed,
            "new_channels_found": new_channels_found,
            "total_yield": total_discovered,
            "last_offset_id": offset_id,
            "last_offset_rate": offset_rate,
            "last_offset_peer_id": offset_peer_id
        }
