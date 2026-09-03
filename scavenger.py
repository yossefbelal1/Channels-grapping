"""
scavenger.py — Production Multi-Source Discovery Engine (Worker C)

Features:
- Multi-Source Telegram Discovery:
  1. Global Message Content Search (messages.searchGlobal)
  2. Public Post & Hashtag Search (channels.searchPosts)
  3. Similar Channel Recommendations (channels.getChannelRecommendations)
  4. Public Directory & Contact Scavenging
- Arabic NLP Keyword Taxonomy & Query Variant Generator
- Resumable Search Pagination via SearchCheckpointManager
- Candidate Identity & Provenance Tracking (ProvenanceManager)
- Distributed Rate Limiting & Health Jitter via TelegramManager
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
from telethon import functions, errors
from telethon.tl.types import Chat, Channel
from tg_manager import TelegramManager

# Discovery Intelligence Modules
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


async def run_global_message_search(
    tg_manager: TelegramManager,
    redis_conn: redis.Redis,
    checkpoint_mgr: SearchCheckpointManager,
    provenance_mgr: ProvenanceManager,
    session_name: str,
    keyword: str,
    shutdown_event: asyncio.Event
) -> int:
    """
    Executes a paginated global message search (messages.searchGlobal) for a given keyword query.
    Extracts channels, groups, and message contexts, persisting checkpoints.
    """
    discovered_count = 0
    query_variants = generate_query_variants(keyword, max_variants=3)

    for query in query_variants:
        if shutdown_event.is_set():
            break

        # Check existing checkpoint
        cp = checkpoint_mgr.get_checkpoint("messages_search_global", query)
        offset_id = cp.get("offset_id", 0) if cp else 0
        offset_rate = cp.get("offset_rate", 0) if cp else 0

        logging.info(f"Global Message Search: '{query}' (offset_id={offset_id})...")

        try:
            res = await tg_manager.search_global_messages(
                session_name=session_name,
                query=query,
                offset_rate=offset_rate,
                offset_id=offset_id,
                limit=100,
                shutdown_event=shutdown_event
            )

            if not res:
                continue

            # Process returned chats / channels
            for chat in getattr(res, 'chats', []):
                username = getattr(chat, 'username', None)
                if not username:
                    continue

                is_group = isinstance(chat, Chat) or (isinstance(chat, Channel) and chat.megagroup)
                channel_link = f"https://t.me/{username}"

                is_new, count, sources = provenance_mgr.record_candidate_discovery(
                    username_or_link=channel_link,
                    source_type="global_search",
                    keyword=query
                )

                payload = json.dumps({
                    "link": channel_link,
                    "source": query,
                    "method": "global_search",
                    "keyword": query,
                    "is_group": is_group,
                    "title": getattr(chat, 'title', ''),
                    "member_count": getattr(chat, 'participants_count', 0),
                    "discovered_count": count,
                    "sources": sources
                })

                target_queue = "queue:normal" if not is_group else "discovered_groups"
                redis_conn.rpush(target_queue, payload)
                discovered_count += 1

            # Process returned messages for mentioned entities
            for msg in getattr(res, 'messages', []):
                msg_text = getattr(msg, 'message', '') or ''
                # Extract forward origin if present
                if getattr(msg, 'fwd_from', None):
                    fwd = msg.fwd_from
                    if getattr(fwd, 'from_name', None):
                        logging.debug(f"Observed forward from: {fwd.from_name}")

            # Update checkpoint
            next_offset_id = getattr(res, 'next_rate', None) or 0
            checkpoint_mgr.save_checkpoint(
                search_type="messages_search_global",
                query_key=query,
                offset_id=next_offset_id,
                total_yield=discovered_count,
                status="completed" if not next_offset_id else "in_progress"
            )

        except Exception as err:
            logging.error(f"Error during global search for '{query}': {err}")

    return discovered_count


async def run_hashtag_post_search(
    tg_manager: TelegramManager,
    redis_conn: redis.Redis,
    provenance_mgr: ProvenanceManager,
    session_name: str,
    hashtag: str,
    shutdown_event: asyncio.Event
) -> int:
    """
    Searches public posts matching specific Arabic trading hashtags.
    """
    discovered_count = 0
    logging.info(f"Hashtag Post Search: #{hashtag}...")

    try:
        res = await tg_manager.search_posts(
            session_name=session_name,
            query="",
            hashtag=hashtag,
            limit=50,
            shutdown_event=shutdown_event
        )

        if not res:
            return 0

        for chat in getattr(res, 'chats', []):
            username = getattr(chat, 'username', None)
            if not username:
                continue

            channel_link = f"https://t.me/{username}"
            is_new, count, sources = provenance_mgr.record_candidate_discovery(
                username_or_link=channel_link,
                source_type="search_posts",
                keyword=f"#{hashtag}"
            )

            payload = json.dumps({
                "link": channel_link,
                "source": f"#{hashtag}",
                "method": "search_posts",
                "keyword": f"#{hashtag}",
                "title": getattr(chat, 'title', ''),
                "discovered_count": count,
                "sources": sources
            })
            redis_conn.rpush("queue:normal", payload)
            discovered_count += 1

    except Exception as err:
        logging.error(f"Error in hashtag search #{hashtag}: {err}")

    return discovered_count


async def run_channel_recommendations_cycle(
    tg_manager: TelegramManager,
    redis_conn: redis.Redis,
    provenance_mgr: ProvenanceManager,
    session_name: str,
    shutdown_event: asyncio.Event
) -> int:
    """
    Pulls top qualified channels from Redis queue 'recommendations:queue'
    and fetches Telegram's official similar-channel recommendations.
    """
    discovered_count = 0
    # Pop up to 10 channels for recommendation crawl per cycle
    for _ in range(10):
        if shutdown_event.is_set():
            break

        channel_data = redis_conn.rpop("recommendations:queue")
        if not channel_data:
            break

        try:
            data = json.loads(channel_data) if isinstance(channel_data, str) else channel_data
            target_username = data.get("username")
            if not target_username:
                continue

            logging.info(f"Fetching Similar Channel Recommendations for @{target_username}...")
            res = await tg_manager.get_channel_recommendations(
                session_name=session_name,
                channel_peer=target_username,
                shutdown_event=shutdown_event
            )

            if not res:
                continue

            for chat in getattr(res, 'chats', []):
                username = getattr(chat, 'username', None)
                if not username:
                    continue

                channel_link = f"https://t.me/{username}"
                is_new, count, sources = provenance_mgr.record_candidate_discovery(
                    username_or_link=channel_link,
                    source_type="recommendation",
                    referrer_channel_id=data.get("channel_id")
                )

                payload = json.dumps({
                    "link": channel_link,
                    "source": f"recommended_by_@{target_username}",
                    "method": "recommendation",
                    "referrer_channel": target_username,
                    "title": getattr(chat, 'title', ''),
                    "discovered_count": count,
                    "sources": sources
                })
                redis_conn.rpush("queue:high", payload)
                discovered_count += 1
                logging.info(f"Discovered Recommended Channel: @{username} (via @{target_username})")

        except Exception as err:
            logging.warning(f"Failed to fetch recommendations: {err}")

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
    Executes a complete multi-source discovery cycle:
    1. Global Message Search with taxonomy mutations & pagination.
    2. Trending Hashtag Post Search.
    3. Similar Channel Recommendations.
    """
    logging.info("Starting Multi-Source Scavenging & Discovery cycle...")
    total_new = 0

    all_keywords = get_all_keywords()
    random.shuffle(all_keywords)

    # 1. Global Message Search Cycle
    for kw in all_keywords[:30]: # Process batch of 30 keywords per cycle
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

        # Adaptive health jitter
        await tg_manager.sleep_adaptive_jitter(session_name, shutdown_event)

        discovered = await run_global_message_search(
            tg_manager=tg_manager,
            redis_conn=redis_conn,
            checkpoint_mgr=checkpoint_mgr,
            provenance_mgr=provenance_mgr,
            session_name=session_name,
            keyword=kw,
            shutdown_event=shutdown_event
        )
        total_new += discovered

    # 2. Hashtag Post Search Cycle
    for tag in random.sample(POPULAR_HASHTAGS, min(5, len(POPULAR_HASHTAGS))):
        if shutdown_event.is_set():
            break
        await tg_manager.sleep_adaptive_jitter(session_name, shutdown_event)
        discovered = await run_hashtag_post_search(
            tg_manager=tg_manager,
            redis_conn=redis_conn,
            provenance_mgr=provenance_mgr,
            session_name=session_name,
            hashtag=tag,
            shutdown_event=shutdown_event
        )
        total_new += discovered

    # 3. Channel Recommendations Cycle
    recs_discovered = await run_channel_recommendations_cycle(
        tg_manager=tg_manager,
        redis_conn=redis_conn,
        provenance_mgr=provenance_mgr,
        session_name=session_name,
        shutdown_event=shutdown_event
    )
    total_new += recs_discovered

    logging.info(f"Multi-Source Scavenging cycle complete. Total candidate entities queued: {total_new}")


async def main():
    load_dotenv()

    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    redis_db = int(os.getenv("REDIS_DB", 0))
    redis_password = os.getenv("REDIS_PASSWORD", None)

    interval = int(os.getenv("SCAVENGER_INTERVAL_SECONDS", 1800)) # 30 min default
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
