"""
scripts/live_telegram_smoke_test.py — Live Telegram Verification Script

Executes live queries against Telegram API using local authenticated session:
1. Arabic Global Search ('توصيات الذهب')
2. English Global Search ('Forex signals')
3. Content-Based Query ('XAUUSD BUY')
4. Multi-Page Pagination (Page 1 -> Page 2 offset progression)
5. SearchPosts Hashtag (#ذهب)
6. SearchPosts Text Query ('XAUUSD')
7. Extraction, Deduplication & Provenance Recording
"""

import os
import sys
import asyncio
from unittest.mock import MagicMock
from telethon import TelegramClient

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tg_manager import TelegramManager
from app.discovery.telegram_global_search import TelegramGlobalSearchEngine
from app.discovery.telegram_post_search import TelegramPostSearchEngine
from app.discovery.provenance import ProvenanceManager


async def run_live_smoke_test():
    session_file = "sessions/validator_session"
    api_id = 39064636
    api_hash = "72d90d8ac46e9293e3d5254d9645e4f9"

    print("==================================================")
    print("LIVE TELEGRAM SMOKE TEST EXECUTION")
    print(f"Target Session: {session_file}.session")
    print("==================================================")

    # 1. Initialize Telethon Client
    client = TelegramClient(session_file, api_id, api_hash)
    await client.connect()
    
    if not await client.is_user_authorized():
        print("[ERROR] Session is not authorized on live Telegram.")
        await client.disconnect()
        return False

    me = await client.get_me()
    print(f"[AUTH SUCCESS] Connected as: {getattr(me, 'first_name', '')} (@{getattr(me, 'username', 'none')}) ID: {me.id}\n")

    # Mock Redis & In-Memory Storage for Clean Candidate Observation
    redis_store = {
        "seen": set(),
        "counts": {},
        "sources": {}
    }
    mock_redis = MagicMock()
    def mock_sadd(key, val):
        if "seen" in key:
            if val in redis_store["seen"]:
                return 0
            redis_store["seen"].add(val)
            return 1
        s = redis_store["sources"].setdefault(key, set())
        s.add(val)
        return 1
    def mock_incr(key):
        c = redis_store["counts"].get(key, 0) + 1
        redis_store["counts"][key] = c
        return c

    discovered_channels = set()
    mock_redis.sadd.side_effect = mock_sadd
    mock_redis.incr.side_effect = mock_incr
    mock_redis.rpush.side_effect = lambda q, val: discovered_channels.add(val)
    mock_redis.get.return_value = None

    # Wire TelegramManager with the live client
    tg_manager = TelegramManager(redis_conn=mock_redis)
    tg_manager._lua_ratelimit = MagicMock(return_value=1)
    tg_manager.clients = {"user_session": client}
    tg_manager.sessions = [{"session_name": "user_session", "api_id": api_id, "api_hash": api_hash}]

    global_engine = TelegramGlobalSearchEngine(tg_manager, mock_redis)
    post_engine = TelegramPostSearchEngine(tg_manager, mock_redis, global_search_engine=global_engine)

    # ── Test 1: Arabic Global Search ──────────────────────────────────────────
    print("--- [1] Arabic Global Search: 'توصيات الذهب' ---")
    try:
        res_ar = await global_engine.search_query_paginated("توصيات الذهب", max_pages=1, limit_per_page=5)
        print(f" -> Found: {res_ar['new_channels_found']} new channels (Total: {res_ar['total_yield']})")
    except Exception as e:
        print(f" -> Global Arabic Error: {e}")

    await asyncio.sleep(2.0)

    # ── Test 2: English Global Search ─────────────────────────────────────────
    print("\n--- [2] English Global Search: 'Forex signals' ---")
    try:
        res_en = await global_engine.search_query_paginated("Forex signals", max_pages=1, limit_per_page=5)
        print(f" -> Found: {res_en['new_channels_found']} new channels (Total: {res_en['total_yield']})")
    except Exception as e:
        print(f" -> Global English Error: {e}")

    await asyncio.sleep(2.0)

    # ── Test 3 & 4: Content-Based Query & Multi-Page Pagination ───────────────
    print("\n--- [3 & 4] Content-Based Query + Pagination: 'XAUUSD BUY' (2 Pages) ---")
    try:
        res_pg = await global_engine.search_query_paginated("XAUUSD BUY", max_pages=2, limit_per_page=5)
        print(f" -> Pages Executed: {res_pg['pages_executed']}")
        print(f" -> New Channels: {res_pg['new_channels_found']}")
        print(f" -> Last Offset ID: {res_pg['last_offset_id']}, Offset Rate: {res_pg['last_offset_rate']}, Offset Peer: {res_pg['last_offset_peer_id']}")
    except Exception as e:
        print(f" -> Content Search Error: {e}")

    await asyncio.sleep(2.0)

    # ── Test 5: SearchPosts Hashtag ───────────────────────────────────────────
    print("\n--- [5] SearchPosts Hashtag: '#ذهب' ---")
    try:
        res_tag = await post_engine.search_hashtag_paginated("ذهب", max_pages=1, limit_per_page=5)
        print(f" -> Search Term: {res_tag.get('search_term', '#ذهب')}")
        print(f" -> New Channels: {res_tag['new_channels_found']}")
    except Exception as e:
        print(f" -> SearchPosts Hashtag Error: {e}")

    await asyncio.sleep(2.0)

    # ── Test 6: SearchPosts Text Query ────────────────────────────────────────
    print("\n--- [6] SearchPosts Text Query: 'XAUUSD' ---")
    try:
        res_txt = await post_engine.search_query_paginated("XAUUSD", max_pages=1, limit_per_page=5)
        print(f" -> Search Term: {res_txt.get('search_term', 'XAUUSD')}")
        print(f" -> New Channels: {res_txt['new_channels_found']}")
    except Exception as e:
        print(f" -> SearchPosts Text Query Error: {e}")

    # ── Deduplication & Provenance Summary ────────────────────────────────────
    print("\n==================================================")
    print("LIVE TELEGRAM DISCOVERY & PROVENANCE SUMMARY")
    print(f"Total Unique Channels Ingested: {len(discovered_channels)}")
    print("Discovered Channel Handles & Provenance:")
    for h in sorted(discovered_channels):
        srcs = list(redis_store["sources"].get(f"provenance:sources:{h.lower()}", ["unknown"]))
        print(f" - @{h} (Sources: {srcs})")
    print("==================================================")

    await client.disconnect()
    return True


if __name__ == "__main__":
    asyncio.run(run_live_smoke_test())
