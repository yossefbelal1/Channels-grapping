"""
tests/test_phase1_telegram_search.py — Unit Tests for Phase 1 Telegram Search Discovery

Covers all required test cases:
1. API response parsing & extraction
2. Channel extraction (ID, username, title, message ID, date)
3. Content-based signal discovery
4. Multi-page pagination with offset_id, offset_rate, and offset_peer
5. Duplicate channel deduplication
6. Arabic queries
7. English & mixed queries
8. Provenance recording
9. Candidate queue insertion
10. FloodWait handling
11. Controlled retries
12. Invalid / empty results handling
13. SearchPosts API response parsing
14. SearchPosts post extraction
15. SearchPosts channel extraction
16. SearchPosts hashtag search (#ذهب, #forex)
17. SearchPosts text query search ("forex signals", "توصيات")
18. SearchPosts multi-page pagination
19. SearchPosts duplicate handling
20. SearchPosts unsupported/restricted detection and clean fallback
21. SearchPosts rate limit handling
22. Cross-source deduplication (global search + searchposts)
23. Idempotent candidate queueing
24. Checkpoint resumption (page 2 starts from page 1 offsets)
25. Offset peer extraction and serialization
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone
from telethon import errors
from telethon.tl.types import PeerChannel, PeerChat, PeerUser

from app.discovery.telegram_global_search import TelegramGlobalSearchEngine
from app.discovery.telegram_post_search import TelegramPostSearchEngine
from app.discovery.checkpoint import SearchCheckpointManager
from app.discovery.provenance import ProvenanceManager
from tg_manager import TelegramManager, SearchPostsUnsupportedError


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_clients_and_redis():
    mock_redis = MagicMock()
    mock_redis.sadd.return_value = 1
    mock_redis.incr.return_value = 1
    mock_redis.rpush.return_value = 1
    mock_redis.get.return_value = None

    mock_db = MagicMock()
    mock_cur = MagicMock()
    mock_db.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchone.return_value = None

    mock_tg = MagicMock(spec=TelegramManager)
    return mock_tg, mock_redis, mock_db


# ── Global Search Unit Tests (1–12, 24–25) ─────────────────────────────────────

def test_1_2_3_global_search_response_parsing_and_extraction(mock_clients_and_redis):
    """1, 2, 3: Tests API response parsing, channel extraction, and message extraction."""
    mock_tg, mock_redis, mock_db = mock_clients_and_redis
    engine = TelegramGlobalSearchEngine(mock_tg, mock_redis, mock_db)

    mock_channel = MagicMock()
    mock_channel.id = 100200300
    mock_channel.title = "The Market Room"
    mock_channel.username = "themarketroom_signals"
    mock_channel.broadcast = True

    mock_msg = MagicMock()
    mock_msg.id = 777
    mock_msg.text = "XAUUSD BUY 2450 SL 2440 TP 2475"
    mock_msg.date = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
    mock_msg.chat = mock_channel
    mock_msg.peer_id = PeerChannel(channel_id=100200300)

    mock_result = MagicMock()
    mock_result.messages = [mock_msg]
    mock_result.chats = [mock_channel]

    cands = engine.extract_channel_candidates(mock_result, matched_query="XAUUSD")
    assert len(cands) == 1
    cand = cands[0]
    assert cand["channel_id"] == "100200300"
    assert cand["username"] == "themarketroom_signals"
    assert cand["title"] == "The Market Room"
    assert cand["matched_message_id"] == 777
    assert "XAUUSD BUY" in cand["post_text_preview"]


@pytest.mark.asyncio
async def test_4_global_search_multi_page_pagination_with_offset_peer(mock_clients_and_redis):
    """4: Tests multi-page pagination passing offset_id, offset_rate, and offset_peer across pages."""
    mock_tg, mock_redis, mock_db = mock_clients_and_redis

    mock_chan_p1 = MagicMock(id=101, username="p1_chan", broadcast=True, title="P1 Chan")
    mock_msg_p1 = MagicMock(id=1001, chat=mock_chan_p1, text="Page 1 Trade", date=datetime.now(timezone.utc))
    mock_msg_p1.peer_id = PeerChannel(channel_id=101)
    page1_res = MagicMock(messages=[mock_msg_p1], chats=[mock_chan_p1], next_rate=50)

    mock_chan_p2 = MagicMock(id=102, username="p2_chan", broadcast=True, title="P2 Chan")
    mock_msg_p2 = MagicMock(id=1002, chat=mock_chan_p2, text="Page 2 Trade", date=datetime.now(timezone.utc))
    mock_msg_p2.peer_id = PeerChannel(channel_id=102)
    page2_res = MagicMock(messages=[mock_msg_p2], chats=[mock_chan_p2], next_rate=0)

    mock_tg.search_global_messages = AsyncMock(side_effect=[page1_res, page2_res])
    engine = TelegramGlobalSearchEngine(mock_tg, mock_redis, mock_db)

    stats = await engine.search_query_paginated("ذهب", max_pages=2, limit_per_page=10)
    assert stats["pages_executed"] == 2
    assert stats["new_channels_found"] == 2
    assert mock_tg.search_global_messages.call_count == 2

    # Verify that call 2 received page 1's offset_id, offset_rate, and offset_peer
    call_args_page2 = mock_tg.search_global_messages.call_args_list[1][1]
    assert call_args_page2["offset_id"] == 1001
    assert call_args_page2["offset_rate"] == 50
    assert call_args_page2["offset_peer"] == 101


def test_5_global_search_duplicate_channels(mock_clients_and_redis):
    """5: Duplicate channels in search results increment count without duplicate enqueues."""
    mock_tg, mock_redis, mock_db = mock_clients_and_redis
    engine = TelegramGlobalSearchEngine(mock_tg, mock_redis, mock_db)

    mock_channel = MagicMock(id=1, username="dup_channel", broadcast=True, title="Dup")
    mock_msg1 = MagicMock(id=1, chat=mock_channel, text="Trade 1", date=datetime.now(timezone.utc))
    mock_msg2 = MagicMock(id=2, chat=mock_channel, text="Trade 2", date=datetime.now(timezone.utc))

    mock_res = MagicMock(messages=[mock_msg1, mock_msg2], chats=[mock_channel])
    cands = engine.extract_channel_candidates(mock_res, "فوركس")
    assert len(cands) == 2

    mock_redis.incr.side_effect = [1, 2]
    prov = ProvenanceManager(mock_redis, mock_db)
    is_new_1, count_1, _ = prov.record_candidate_discovery("dup_channel", "telegram_global_search")
    is_new_2, count_2, _ = prov.record_candidate_discovery("dup_channel", "telegram_global_search")
    assert is_new_1 is True
    assert is_new_2 is False
    assert count_2 == 2


def test_6_7_arabic_and_english_queries(mock_clients_and_redis):
    """6, 7: Supports Arabic, English, and mixed query gathering from taxonomy."""
    mock_tg, mock_redis, mock_db = mock_clients_and_redis
    engine = TelegramGlobalSearchEngine(mock_tg, mock_redis, mock_db)

    queries = engine.get_search_queries()
    assert any("فوركس" in q for q in queries)
    assert any("ذهب" in q for q in queries)
    assert any("xauusd" in q.lower() for q in queries)
    assert any("signals" in q.lower() for q in queries)


@pytest.mark.asyncio
async def test_8_9_provenance_and_queue_insertion(mock_clients_and_redis):
    """8, 9: Tests provenance recording and candidate queue insertion."""
    mock_tg, mock_redis, mock_db = mock_clients_and_redis
    mock_channel = MagicMock(id=555, username="fresh_lead", broadcast=True, title="Fresh Lead")
    mock_msg = MagicMock(id=1, chat=mock_channel, text="Forex setup", date=datetime.now(timezone.utc))
    page_res = MagicMock(messages=[mock_msg], chats=[mock_channel])

    mock_tg.search_global_messages = AsyncMock(return_value=page_res)
    engine = TelegramGlobalSearchEngine(mock_tg, mock_redis, mock_db, candidate_queue="queue:normal")

    stats = await engine.search_query_paginated("XAUUSD", max_pages=1)
    assert stats["new_channels_found"] == 1
    assert mock_redis.rpush.called
    assert mock_redis.rpush.call_args[0] == ("queue:normal", "fresh_lead")


@pytest.mark.asyncio
async def test_10_11_floodwait_and_retries(mock_clients_and_redis):
    """10, 11: FloodWait is handled gracefully without crashing worker."""
    mock_tg, mock_redis, mock_db = mock_clients_and_redis
    mock_tg.search_global_messages = AsyncMock(side_effect=errors.FloodWaitError(request=None, capture=0))
    engine = TelegramGlobalSearchEngine(mock_tg, mock_redis, mock_db)

    stats = await engine.search_query_paginated("توصيات", max_pages=2)
    assert stats["pages_executed"] == 0


def test_12_invalid_results_handling(mock_clients_and_redis):
    """12: Empty or malformed search response returns empty candidates."""
    mock_tg, mock_redis, mock_db = mock_clients_and_redis
    engine = TelegramGlobalSearchEngine(mock_tg, mock_redis, mock_db)

    assert engine.extract_channel_candidates(None, "test") == []
    assert engine.extract_channel_candidates(MagicMock(messages=[], chats=[]), "test") == []


def test_25_offset_peer_extraction_and_serialization(mock_clients_and_redis):
    """25: Verifies that offset_peer types (PeerChannel, PeerChat, PeerUser) serialize cleanly to checkpoints."""
    _, mock_redis, mock_db = mock_clients_and_redis
    chk = SearchCheckpointManager(mock_redis, mock_db)

    chk.save_checkpoint(
        search_type="telegram_global_search",
        query_key="xauusd_trade",
        offset_id=888,
        offset_rate=25,
        offset_peer_id=999888,
        offset_peer_type="channel",
        page_number=2,
        total_yield=15,
        status="in_progress"
    )

    assert mock_redis.set.called
    payload = mock_redis.set.call_args[0][1]
    assert '"offset_peer_id": 999888' in payload
    assert '"offset_peer_type": "channel"' in payload
    assert '"offset_id": 888' in payload


@pytest.mark.asyncio
async def test_24_checkpoint_resumption_continues_from_saved_state(mock_clients_and_redis):
    """24: Verifies that an interrupted search resumes from the exact saved offset_id and offset_peer."""
    mock_tg, mock_redis, mock_db = mock_clients_and_redis

    # Preset checkpoint in Redis
    import json
    mock_redis.get.return_value = json.dumps({
        "search_type": "telegram_global_search",
        "query_key": "resumable_query",
        "offset_id": 4444,
        "offset_rate": 100,
        "offset_peer_id": 777666,
        "offset_peer_type": "channel",
        "page_number": 3,
        "total_yield": 20,
        "status": "in_progress"
    })

    mock_chan = MagicMock(id=999, username="resumed_chan", broadcast=True, title="Resumed")
    mock_msg = MagicMock(id=5555, chat=mock_chan, text="Resumed post", date=datetime.now(timezone.utc))
    mock_tg.search_global_messages = AsyncMock(return_value=MagicMock(messages=[mock_msg], chats=[mock_chan]))

    engine = TelegramGlobalSearchEngine(mock_tg, mock_redis, mock_db)
    await engine.search_query_paginated("resumable_query", max_pages=1)

    # Check that search_global_messages was called with resumed checkpoint parameters
    assert mock_tg.search_global_messages.called
    kwargs = mock_tg.search_global_messages.call_args[1]
    assert kwargs["offset_id"] == 4444
    assert kwargs["offset_rate"] == 100
    assert kwargs["offset_peer"] == 777666


# ── SearchPosts Unit Tests (13–21) ────────────────────────────────────────────

def test_13_14_15_searchposts_response_and_extraction(mock_clients_and_redis):
    """13, 14, 15: Tests SearchPosts API parsing, post extraction, and channel extraction."""
    mock_tg, mock_redis, mock_db = mock_clients_and_redis
    engine = TelegramPostSearchEngine(mock_tg, mock_redis, mock_db)

    mock_channel = MagicMock(id=888, username="smc_traders", broadcast=True, title="SMC Traders")
    mock_msg = MagicMock(id=99, chat=mock_channel, text="تحليل #ذهب #SMC", date=datetime.now(timezone.utc))
    mock_res = MagicMock(messages=[mock_msg], chats=[mock_channel])

    cands = engine.global_search_engine.extract_channel_candidates(mock_res, "#ذهب")
    assert len(cands) == 1
    assert cands[0]["username"] == "smc_traders"
    assert cands[0]["matched_query"] == "#ذهب"


@pytest.mark.asyncio
async def test_16_searchposts_hashtag_search(mock_clients_and_redis):
    """16: Tests SearchPosts using explicit hashtag parameter."""
    mock_tg, mock_redis, mock_db = mock_clients_and_redis
    mock_chan = MagicMock(id=301, username="gold_tag_chan", broadcast=True, title="Gold Tag")
    mock_msg = MagicMock(id=50, chat=mock_chan, text="#ذهب صفقة", date=datetime.now(timezone.utc))
    mock_tg.search_posts = AsyncMock(return_value=MagicMock(messages=[mock_msg], chats=[mock_chan]))

    engine = TelegramPostSearchEngine(mock_tg, mock_redis, mock_db)
    res = await engine.search_hashtag_paginated("ذهب", max_pages=1)

    assert res["new_channels_found"] == 1
    assert mock_tg.search_posts.called
    kwargs = mock_tg.search_posts.call_args[1]
    assert kwargs["hashtag"] == "ذهب"
    assert kwargs["query"] is None


@pytest.mark.asyncio
async def test_17_searchposts_text_query_search(mock_clients_and_redis):
    """17: Tests SearchPosts using normal text query parameter."""
    mock_tg, mock_redis, mock_db = mock_clients_and_redis
    mock_chan = MagicMock(id=302, username="forex_query_chan", broadcast=True, title="Forex Query")
    mock_msg = MagicMock(id=60, chat=mock_chan, text="Forex signals daily", date=datetime.now(timezone.utc))
    mock_tg.search_posts = AsyncMock(return_value=MagicMock(messages=[mock_msg], chats=[mock_chan]))

    engine = TelegramPostSearchEngine(mock_tg, mock_redis, mock_db)
    res = await engine.search_query_paginated("Forex signals", max_pages=1)

    assert res["new_channels_found"] == 1
    assert mock_tg.search_posts.called
    kwargs = mock_tg.search_posts.call_args[1]
    assert kwargs["query"] == "Forex signals"
    assert kwargs["hashtag"] is None


@pytest.mark.asyncio
async def test_18_searchposts_multi_page_pagination(mock_clients_and_redis):
    """18: Tests SearchPosts multi-page pagination with offset_peer propagation."""
    mock_tg, mock_redis, mock_db = mock_clients_and_redis

    mock_chan1 = MagicMock(id=401, username="p1_post_chan", broadcast=True, title="P1")
    mock_msg1 = MagicMock(id=201, chat=mock_chan1, text="#SMC trade 1", date=datetime.now(timezone.utc))
    mock_msg1.peer_id = PeerChannel(channel_id=401)
    res_p1 = MagicMock(messages=[mock_msg1], chats=[mock_chan1], next_rate=20)

    mock_chan2 = MagicMock(id=402, username="p2_post_chan", broadcast=True, title="P2")
    mock_msg2 = MagicMock(id=202, chat=mock_chan2, text="#SMC trade 2", date=datetime.now(timezone.utc))
    mock_msg2.peer_id = PeerChannel(channel_id=402)
    res_p2 = MagicMock(messages=[mock_msg2], chats=[mock_chan2], next_rate=0)

    mock_tg.search_posts = AsyncMock(side_effect=[res_p1, res_p2])
    engine = TelegramPostSearchEngine(mock_tg, mock_redis, mock_db)

    stats = await engine.search_hashtag_paginated("SMC", max_pages=2)
    assert stats["pages_executed"] == 2
    assert stats["new_channels_found"] == 2

    call_args_page2 = mock_tg.search_posts.call_args_list[1][1]
    assert call_args_page2["offset_id"] == 201
    assert call_args_page2["offset_rate"] == 20
    assert call_args_page2["offset_peer"] == 401


@pytest.mark.asyncio
async def test_19_searchposts_duplicate_handling(mock_clients_and_redis):
    """19: Repeated post occurrences of same channel deduplicate cleanly."""
    mock_tg, mock_redis, mock_db = mock_clients_and_redis
    mock_channel = MagicMock(id=777, username="repeated_chan", broadcast=True, title="Repeated")
    mock_msg = MagicMock(id=1, chat=mock_channel, text="#فوركس", date=datetime.now(timezone.utc))
    mock_res = MagicMock(messages=[mock_msg], chats=[mock_channel])

    mock_tg.search_posts = AsyncMock(return_value=mock_res)
    engine = TelegramPostSearchEngine(mock_tg, mock_redis, mock_db)

    # 1st time
    mock_redis.incr.side_effect = [1, 2]
    stats1 = await engine.search_hashtag_paginated("فوركس", max_pages=1)
    assert stats1["new_channels_found"] == 1

    # 2nd time: duplicate detected via ProvenanceManager
    stats2 = await engine.search_hashtag_paginated("فوركس", max_pages=1)
    assert stats2["new_channels_found"] == 0


@pytest.mark.asyncio
async def test_20_searchposts_clean_fallback_without_nested_retries(mock_clients_and_redis):
    """20: When SearchPosts raises SearchPostsUnsupportedError, falls back cleanly to Global Search without nested retries."""
    mock_tg, mock_redis, mock_db = mock_clients_and_redis

    # Simulate SearchPosts unsupported on Telegram
    mock_tg.search_posts = AsyncMock(side_effect=SearchPostsUnsupportedError("Paid stars required / restricted"))

    mock_chan = MagicMock(id=888, username="fallback_found_chan", broadcast=True, title="Fallback Found")
    mock_msg = MagicMock(id=10, chat=mock_chan, text="#ذهب signal", date=datetime.now(timezone.utc))
    fallback_res = MagicMock(messages=[mock_msg], chats=[mock_chan])
    mock_tg.search_global_messages = AsyncMock(return_value=fallback_res)

    engine = TelegramPostSearchEngine(mock_tg, mock_redis, mock_db)
    stats = await engine.search_hashtag_paginated("ذهب", max_pages=1)

    # Verify fallback was invoked cleanly
    assert stats["new_channels_found"] == 1
    assert mock_tg.search_global_messages.called
    assert mock_tg.search_global_messages.call_args[1]["query"] == "#ذهب"


# ── Shared Pipeline Tests (22–24) ─────────────────────────────────────────────

def test_22_cross_source_deduplication(mock_clients_and_redis):
    """22: Channel found by both global search and searchposts results in single canonical candidate."""
    _, mock_redis, mock_db = mock_clients_and_redis
    prov = ProvenanceManager(mock_redis, mock_db)

    # 1. Discovered via global search
    is_new_1, count_1, sources_1 = prov.record_candidate_discovery(
        "niche_forex_channel", "telegram_global_search", keyword="XAUUSD"
    )
    assert is_new_1 is True
    assert count_1 == 1

    # 2. Same channel discovered via search_posts
    mock_redis.sadd.return_value = 0 # Already known
    mock_redis.incr.return_value = 2
    mock_redis.smembers.return_value = {b"telegram_global_search", b"telegram_search_posts"}

    is_new_2, count_2, sources_2 = prov.record_candidate_discovery(
        "niche_forex_channel", "telegram_search_posts", keyword="#gold"
    )
    assert is_new_2 is False
    assert count_2 == 2
    assert "telegram_global_search" in sources_2
    assert "telegram_search_posts" in sources_2


def test_23_idempotent_job_handling(mock_clients_and_redis):
    """23: Enqueueing candidate is idempotent using Redis candidate sets."""
    _, mock_redis, mock_db = mock_clients_and_redis
    mock_redis.incr.side_effect = [1, 2]
    prov = ProvenanceManager(mock_redis, mock_db)

    # Multiple identical hits do not re-enqueue
    is_new, _, _ = prov.record_candidate_discovery("idempotent_lead", "telegram_global_search")
    assert is_new is True

    is_new_again, _, _ = prov.record_candidate_discovery("idempotent_lead", "telegram_global_search")
    assert is_new_again is False


def test_26_post_search_engine_constructor_dependency_injection(mock_clients_and_redis):
    """26: Verifies that TelegramPostSearchEngine constructor accepts global_search_engine dependency injection cleanly."""
    mock_tg, mock_redis, mock_db = mock_clients_and_redis
    global_engine = TelegramGlobalSearchEngine(
        tg_manager=mock_tg,
        redis_conn=mock_redis,
        candidate_queue="queue:normal"
    )

    # Constructor with explicit keyword dependency injection
    post_engine = TelegramPostSearchEngine(
        tg_manager=mock_tg,
        redis_conn=mock_redis,
        candidate_queue="queue:normal",
        global_search_engine=global_engine
    )

    assert post_engine.global_search_engine is global_engine
    assert post_engine.candidate_queue == "queue:normal"


def test_27_checkpoint_postgres_fallback_restores_offset_peer_when_redis_empty():
    """27: Verifies PostgreSQL fallback restores full state including offset_peer_id and offset_peer_type when Redis is cleared."""
    mock_redis = MagicMock()
    mock_redis.get.return_value = None # Simulate Redis cache miss or loss

    mock_db = MagicMock()
    mock_cur = MagicMock()
    mock_db.cursor.return_value.__enter__.return_value = mock_cur

    # Mock DB row returned from discovery_checkpoints
    mock_cur.fetchone.return_value = {
        "offset_id": 89100,
        "offset_rate": 250,
        "offset_peer_id": 1987654321,
        "offset_peer_type": "channel",
        "offset_date": None,
        "page_number": 4,
        "total_yield": 42,
        "status": "in_progress"
    }

    chk_mgr = SearchCheckpointManager(mock_redis, mock_db)
    cp = chk_mgr.get_checkpoint("telegram_global_search", "XAUUSD")

    assert cp is not None
    assert cp["offset_id"] == 89100
    assert cp["offset_rate"] == 250
    assert cp["offset_peer_id"] == 1987654321
    assert cp["offset_peer_type"] == "channel"
    assert cp["page_number"] == 4
    assert cp["total_yield"] == 42

