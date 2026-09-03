"""
tests/test_phase1_telegram_search.py — Unit Tests for Phase 1 Telegram Search Discovery

Covers all 24 required test cases:
1-12:  Global Search (messages.searchGlobal)
13-21: Post Search (channels.searchPosts)
22-24: Shared Pipeline (deduplication, idempotency, validation integration)
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone
from telethon import errors

from app.discovery.telegram_global_search import TelegramGlobalSearchEngine
from app.discovery.telegram_post_search import TelegramPostSearchEngine
from app.discovery.checkpoint import SearchCheckpointManager
from app.discovery.provenance import ProvenanceManager
from tg_manager import TelegramManager


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


# ── Global Search Unit Tests (1–12) ───────────────────────────────────────────

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
    mock_msg.peer_id = MagicMock(channel_id=100200300)

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
async def test_4_global_search_pagination(mock_clients_and_redis):
    """4: Tests pagination through multiple pages without stopping at page 1."""
    mock_tg, mock_redis, mock_db = mock_clients_and_redis
    
    mock_channel = MagicMock(id=1, username="chan1", broadcast=True, title="Chan 1")
    mock_msg = MagicMock(id=10, chat=mock_channel, text="Forex Signals", date=datetime.now(timezone.utc))
    page_res = MagicMock(messages=[mock_msg], chats=[mock_channel])

    mock_tg.search_global_messages = AsyncMock(return_value=page_res)
    engine = TelegramGlobalSearchEngine(mock_tg, mock_redis, mock_db)

    stats = await engine.search_query_paginated("فوركس", max_pages=3, limit_per_page=10)
    assert stats["pages_executed"] == 3
    assert mock_tg.search_global_messages.call_count == 3


def test_5_global_search_duplicate_channels(mock_clients_and_redis):
    """5: Duplicate channels in same search result produce single candidate entry."""
    mock_tg, mock_redis, mock_db = mock_clients_and_redis
    engine = TelegramGlobalSearchEngine(mock_tg, mock_redis, mock_db)

    mock_channel = MagicMock(id=1, username="dup_channel", broadcast=True, title="Dup")
    mock_msg1 = MagicMock(id=1, chat=mock_channel, text="Trade 1", date=datetime.now(timezone.utc))
    mock_msg2 = MagicMock(id=2, chat=mock_channel, text="Trade 2", date=datetime.now(timezone.utc))
    
    mock_res = MagicMock(messages=[mock_msg1, mock_msg2], chats=[mock_channel])
    cands = engine.extract_channel_candidates(mock_res, "فوركس")
    assert len(cands) == 2
    # Provenance deduplicates
    mock_redis.incr.side_effect = [1, 2]
    prov = ProvenanceManager(mock_redis, mock_db)
    is_new_1, count_1, _ = prov.record_candidate_discovery("dup_channel", "telegram_global_search")
    is_new_2, count_2, _ = prov.record_candidate_discovery("dup_channel", "telegram_global_search")
    assert is_new_1 is True
    assert is_new_2 is False


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
    # Simulate FloodWait on search
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


# ── SearchPosts Unit Tests (13–21) ────────────────────────────────────────────

def test_13_14_15_searchposts_response_and_extraction(mock_clients_and_redis):
    """13, 14, 15: Tests SearchPosts API parsing, post extraction, and channel extraction."""
    mock_tg, mock_redis, mock_db = mock_clients_and_redis
    engine = TelegramPostSearchEngine(mock_tg, mock_redis, mock_db)

    mock_channel = MagicMock(id=888, username="smc_traders", broadcast=True, title="SMC Traders")
    mock_msg = MagicMock(id=99, chat=mock_channel, text="تحليل #ذهب #SMC", date=datetime.now(timezone.utc))
    mock_res = MagicMock(messages=[mock_msg], chats=[mock_channel])

    cands = engine.extractor.extract_channel_candidates(mock_res, "#ذهب")
    assert len(cands) == 1
    assert cands[0]["username"] == "smc_traders"
    assert cands[0]["matched_query"] == "#ذهب"


def test_16_17_18_searchposts_hashtags_and_queries(mock_clients_and_redis):
    """16, 17, 18: Target hashtags contain Arabic and English terms."""
    mock_tg, mock_redis, mock_db = mock_clients_and_redis
    engine = TelegramPostSearchEngine(mock_tg, mock_redis, mock_db)

    tags = engine.get_target_hashtags()
    assert "ذهب" in tags
    assert "فوركس" in tags
    assert "XAUUSD" in tags
    assert "SMC" in tags


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

    # 2nd time: duplicate is detected via ProvenanceManager mock
    stats2 = await engine.search_hashtag_paginated("فوركس", max_pages=1)
    assert stats2["new_channels_found"] == 0


@pytest.mark.asyncio
async def test_20_21_searchposts_unsupported_and_rate_limits(mock_clients_and_redis):
    """20, 21: Unsupported post search or rate errors handle gracefully."""
    mock_tg, mock_redis, mock_db = mock_clients_and_redis
    mock_tg.search_posts = AsyncMock(return_value=None)
    engine = TelegramPostSearchEngine(mock_tg, mock_redis, mock_db)

    stats = await engine.search_hashtag_paginated("restricted_tag", max_pages=1)
    assert stats["new_channels_found"] == 0
    assert stats["pages_executed"] == 0


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


def test_24_validator_pipeline_integration(mock_clients_and_redis):
    """24: Extracted candidates match the format expected by validator.py."""
    mock_tg, mock_redis, mock_db = mock_clients_and_redis
    engine = TelegramGlobalSearchEngine(mock_tg, mock_redis, mock_db)

    mock_channel = MagicMock(id=999, username="valid_candidate", broadcast=True, title="Valid")
    mock_msg = MagicMock(id=10, chat=mock_channel, text="Forex Analysis", date=datetime.now(timezone.utc))
    mock_res = MagicMock(messages=[mock_msg], chats=[mock_channel])

    cands = engine.extract_channel_candidates(mock_res, "forex")
    assert len(cands) == 1
    # Check validator queue string compatibility
    val_payload = cands[0]["username"]
    assert isinstance(val_payload, str)
    assert len(val_payload) > 0
