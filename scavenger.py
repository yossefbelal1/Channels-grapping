"""
scavenger.py — Production Multi-Source Discovery Engine (Worker C)

Unified Phase 1 Discovery Pipeline:
1. Existing Contacts Search: functions.contacts.SearchRequest(q=keyword, limit=100)
2. Telegram Global Search: app.discovery.telegram_global_search.TelegramGlobalSearchEngine (messages.searchGlobal)
3. Telegram Post Search: app.discovery.telegram_post_search.TelegramPostSearchEngine (channels.searchPosts)
                     ↓
        Canonical Candidate Resolution
                     ↓
        Atomic Multi-Source Deduplication (seen_channels & ProvenanceManager)
                     ↓
        Shared Redis Candidate Queue (queue:normal)
                     ↓
        Existing Lead Validator (validator.py)
"""

import os
import sys
import json
import asyncio
import signal
import logging
import random
from datetime import datetime, timezone
from dotenv import load_dotenv
import redis
from telethon import functions
from telethon.tl.types import Chat, Channel
from tg_manager import TelegramManager

# Discovery Intelligence & Search Engines
from app.discovery.telegram_global_search import TelegramGlobalSearchEngine
from app.discovery.telegram_post_search import TelegramPostSearchEngine
from app.discovery.arabic_normalizer import generate_query_variants, normalize_arabic_text
from app.discovery.taxonomy import get_all_keywords, KEYWORD_TAXONOMY
from app.discovery.checkpoint import SearchCheckpointManager
from app.discovery.provenance import ProvenanceManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [SCAVENGER] [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Top Trading Hashtags for Global Post Search
POPULAR_HASHTAGS = [
    "ذهب", "فوركس", "xauusd", "توصيات_ذهب", "تداول_العملات",
    "توصيات_فوركس", "smc", "ict", "تحليل_فني", "سكالبينج",
    "حسابات_ممولة", "ادارة_محافظ", "نسخ_صفقات", "بيتكوين"
]


async def run_contacts_directory_search(
    tg_manager: TelegramManager,
    redis_conn: redis.Redis,
    provenance_mgr: ProvenanceManager,
    session_name: str,
    keyword: str,
    shutdown_event: asyncio.Event,
    candidate_queue: str = "queue:normal"
) -> int:
    """
    Source 1: Existing Contacts Directory Search (functions.contacts.SearchRequest).
    Discovers channels and public groups matching keywords in Telegram's public contact directory.
    """
    discovered_count = 0
    logging.info(f"[ContactsSearch] Searching directory for keyword: '{keyword}'...")

    async def _req(cl):
        return await cl(functions.contacts.SearchRequest(q=keyword, limit=100))

    try:
        res = await tg_manager.execute_request(
            session_name,
            _req,
            shutdown_event=shutdown_event
        )

        if not res or not hasattr(res, 'chats'):
            return 0

        for chat in res.chats:
            username = getattr(chat, 'username', None)
            if not username:
                continue

            channel_link = f"https://t.me/{username}"
            is_new, count, sources = provenance_mgr.record_candidate_discovery(
                username_or_link=channel_link,
                source_type="contacts_search",
                keyword=keyword,
                metadata={
                    "channel_id": str(getattr(chat, 'id', '')),
                    "title": getattr(chat, 'title', '')
                }
            )

            if is_new:
                redis_conn.rpush(candidate_queue, username)
                discovered_count += 1
                logging.info(f"[ContactsSearch] Enqueued new candidate: @{username} (source: contacts_search, keyword: '{keyword}')")

    except Exception as err:
        logging.warning(f"[ContactsSearch] Directory search for '{keyword}' failed: {err}")

    return discovered_count


async def run_scavenger(
    tg_manager: TelegramManager,
    redis_conn: redis.Redis,
    checkpoint_mgr: SearchCheckpointManager,
    provenance_mgr: ProvenanceManager,
    session_name: str,
    shutdown_event: asyncio.Event
):
    """
    Executes a complete, unified discovery cycle:
    1. Existing Directory/Contacts Search (functions.contacts.SearchRequest)
    2. Real Telegram Global Search (messages.searchGlobal via TelegramGlobalSearchEngine)
    3. Real Telegram Post Search (channels.searchPosts via TelegramPostSearchEngine)
    All three feed the exact SAME candidate queue ('queue:normal') with atomic deduplication.
    """
    logging.info("Starting Multi-Source Scavenging & Discovery cycle...")
    total_new = 0

    candidate_queue = "queue:normal"

    # Instantiate dedicated Phase 1 Search Engines
    global_search_engine = TelegramGlobalSearchEngine(
        tg_manager=tg_manager,
        redis_conn=redis_conn,
        candidate_queue=candidate_queue
    )
    post_search_engine = TelegramPostSearchEngine(
        tg_manager=tg_manager,
        redis_conn=redis_conn,
        candidate_queue=candidate_queue,
        global_search_engine=global_search_engine
    )

    all_keywords = get_all_keywords()
    random.shuffle(all_keywords)

    # ── Source 1: Existing Contacts Search ────────────────────────────────────
    for kw in all_keywords[:5]:
        if shutdown_event.is_set():
            break
        await tg_manager.sleep_adaptive_jitter(session_name, shutdown_event)
        new_contacts = await run_contacts_directory_search(
            tg_manager=tg_manager,
            redis_conn=redis_conn,
            provenance_mgr=provenance_mgr,
            session_name=session_name,
            keyword=kw,
            shutdown_event=shutdown_event,
            candidate_queue=candidate_queue
        )
        total_new += new_contacts

    # ── Source 2: Telegram Global Content Search (messages.searchGlobal) ──────
    for kw in all_keywords[:15]:
        if shutdown_event.is_set():
            break

        # Check backpressure
        try:
            q_len = redis_conn.llen("queue:normal") + redis_conn.llen("queue:high")
            while q_len >= 1200 and not shutdown_event.is_set():
                logging.warning(f"Backpressure active ({q_len} queued). Pausing discovery for 25s...")
                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=25)
                except asyncio.TimeoutError:
                    pass
                q_len = redis_conn.llen("queue:normal") + redis_conn.llen("queue:high")
        except Exception:
            pass

        await tg_manager.sleep_adaptive_jitter(session_name, shutdown_event)
        logging.info(f"[Scavenger] Running Telegram Global Search for '{kw}'...")
        stats_global = await global_search_engine.search_query_paginated(
            query=kw,
            max_pages=2,
            limit_per_page=50,
            shutdown_event=shutdown_event
        )
        total_new += stats_global.get("new_channels_found", 0)

    # ── Source 3: Telegram Public Post Search (channels.searchPosts) ──────────
    for tag in random.sample(POPULAR_HASHTAGS, min(5, len(POPULAR_HASHTAGS))):
        if shutdown_event.is_set():
            break
        await tg_manager.sleep_adaptive_jitter(session_name, shutdown_event)
        logging.info(f"[Scavenger] Running Telegram Post Search for hashtag #{tag}...")
        stats_tag = await post_search_engine.search_hashtag_paginated(
            hashtag=tag,
            max_pages=2,
            limit_per_page=50,
            shutdown_event=shutdown_event
        )
        total_new += stats_tag.get("new_channels_found", 0)

    logging.info(f"Multi-Source Scavenging cycle complete. Total new candidate entities queued: {total_new}")


async def main():
    load_dotenv()

    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    redis_db = int(os.getenv("REDIS_DB", 0))
    redis_password = os.getenv("REDIS_PASSWORD", None)

    interval = int(os.getenv("SCAVENGER_INTERVAL_SECONDS", 1800))
    session_scavenger = os.getenv("SESSION_SCAVENGER", "scavenger_session")

    logging.info(f"Connecting to Redis at {redis_host}:{redis_port}...")
    try:
        redis_conn = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True
        )
        redis_conn.ping()
        logging.info("Redis connected successfully.")
    except Exception as e:
        logging.error(f"Failed to connect to Redis: {e}")
        sys.exit(1)

    checkpoint_mgr = SearchCheckpointManager(redis_conn)
    provenance_mgr = ProvenanceManager(redis_conn)

    logging.info(f"Initializing Telegram Manager for session: '{session_scavenger}'...")
    tg_manager = TelegramManager(redis_conn, session_name=session_scavenger, worker_type="scavenger")
    await tg_manager.start_all()

    shutdown_event = asyncio.Event()

    def stop_worker():
        logging.info("Graceful shutdown signal received.")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_worker)
    except NotImplementedError:
        pass

    logging.info(f"Scavenger Multi-Source Discovery Engine is active. Cycle interval: {interval}s.")

    while not shutdown_event.is_set():
        try:
            await run_scavenger(
                tg_manager=tg_manager,
                redis_conn=redis_conn,
                checkpoint_mgr=checkpoint_mgr,
                provenance_mgr=provenance_mgr,
                session_name=session_scavenger,
                shutdown_event=shutdown_event
            )
        except Exception as e:
            logging.error(f"Error in scavenger discovery cycle: {e}", exc_info=True)

        logging.info(f"Sleeping for {interval}s until next scheduled discovery cycle...")
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass

    await tg_manager.disconnect_all()
    redis_conn.close()
    logging.info("Scavenger worker stopped cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Terminated by user.")
    except Exception as e:
        logging.critical(f"FATAL WORKER ERROR: {e}")
        sys.exit(1)
