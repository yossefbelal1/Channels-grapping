"""
tests/test_phase1_search_integration.py — Integration Test for Phase 1 Search Pipeline

Demonstrates full flow:
1. Contacts Directory Search (functions.contacts.SearchRequest) -> Canonical Channel -> Dedupe -> Candidate Queue
2. Global Search (messages.searchGlobal) -> Result -> Canonical Channel -> Dedupe -> Candidate Queue -> Validation
3. SearchPosts (channels.searchPosts) -> Result -> Canonical Channel -> Dedupe -> Candidate Queue -> Validation
4. Production scavenger orchestration executing all 3 sources into shared candidate queue ('queue:normal')
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone

from app.discovery.telegram_global_search import TelegramGlobalSearchEngine
from app.discovery.telegram_post_search import TelegramPostSearchEngine
from app.discovery.provenance import ProvenanceManager
from app.discovery.checkpoint import SearchCheckpointManager
from app.scoring.engine import LeadScoringEngine
from app.validator.contact_extractor import extract_contacts
from tg_manager import TelegramManager
from scavenger import run_scavenger, run_contacts_directory_search


@pytest.mark.asyncio
async def test_full_phase1_search_integration_flow():
    # ── 1. Mock Infrastructure ──
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

    # ── 2. Global Search Flow ──
    # Simulates finding channel 'AlphaForexTraders' via messages.searchGlobal query 'توصيات الذهب'
    mock_channel_1 = MagicMock(id=111222, username="AlphaForexTraders", broadcast=True, title="Alpha Forex Hub")
    mock_msg_1 = MagicMock(
        id=501,
        chat=mock_channel_1,
        text="صفقة شراء XAUUSD الهدف 2680 وقف الخسارة 2640 #ذهب للإدارة: @AlphaManager",
        date=datetime.now(timezone.utc)
    )
    search_global_res = MagicMock(messages=[mock_msg_1], chats=[mock_channel_1])
    mock_tg.search_global_messages = AsyncMock(return_value=search_global_res)

    global_engine = TelegramGlobalSearchEngine(mock_tg, mock_redis, mock_db, candidate_queue="queue:normal")
    res1 = await global_engine.search_query_paginated("توصيات الذهب", max_pages=1)
    
    assert res1["new_channels_found"] == 1
    # Check that candidate was enqueued into Redis
    assert mock_redis.rpush.called
    assert mock_redis.rpush.call_args[0] == ("queue:normal", "AlphaForexTraders")

    # ── 3. SearchPosts Flow ──
    # Simulates finding channel 'SMC_Sniper_Arabic' via channels.searchPosts query '#SMC'
    mock_channel_2 = MagicMock(id=333444, username="SMC_Sniper_Arabic", broadcast=True, title="SMC Sniper Arabic")
    mock_msg_2 = MagicMock(
        id=802,
        chat=mock_channel_2,
        text="تحليل مناطق Order Block على اليورو دولار #SMC #Forex",
        date=datetime.now(timezone.utc)
    )
    search_posts_res = MagicMock(messages=[mock_msg_2], chats=[mock_channel_2])
    mock_tg.search_posts = AsyncMock(return_value=search_posts_res)

    post_engine = TelegramPostSearchEngine(mock_tg, mock_redis, mock_db, candidate_queue="queue:normal")
    res2 = await post_engine.search_hashtag_paginated("SMC", max_pages=1)

    assert res2["new_channels_found"] == 1
    assert mock_redis.rpush.call_args[0] == ("queue:normal", "SMC_Sniper_Arabic")

    # ── 4. Validation Pipeline Integration ──
    # Simulates validator consuming the candidate and validating Stage 1 & Stage 2
    bio = "قناة متخصصة في تداول الفوركس والذهب. للإدارة: @AlphaManager واتساب: https://wa.me/201207500631"
    stage1_ok, reason, score = LeadScoringEngine.evaluate_stage_1(
        title="Alpha Forex Hub",
        description=bio,
        username="AlphaForexTraders",
        member_count=300 # Small channel
    )
    assert stage1_ok is True

    contacts = extract_contacts(text=mock_msg_1.text, description=bio, channel_username="AlphaForexTraders")
    assert contacts["admin_username"] == "AlphaManager"
    assert contacts["whatsapp"] == "201207500631"

    stage2_scores = LeadScoringEngine.evaluate_stage_2(
        title="Alpha Forex Hub",
        description=bio,
        recent_posts=[mock_msg_1.text],
        member_count=300,
        has_contact=True,
        contact_types=["admin", "whatsapp"],
        posts_24h=1,
        posts_7d=8,
        posts_30d=25,
        last_post_at=datetime.now(timezone.utc)
    )

    assert stage2_scores.forex_score >= 15 or stage2_scores.gold_score >= 15
    assert stage2_scores.final_score >= 40
    assert stage2_scores.tier in ["Tier_A", "Tier_B", "Tier_C"]

    print("Phase 1 Search Discovery & Validation Integration Pipeline test passed cleanly!")


@pytest.mark.asyncio
async def test_scavenger_production_worker_executes_all_three_sources(monkeypatch):
    """
    Proves that the real production discovery entrypoint (scavenger.py:run_scavenger)
    executes all three discovery sources:
    1. Contacts Directory Search (functions.contacts.SearchRequest)
    2. TelegramGlobalSearchEngine (messages.searchGlobal)
    3. TelegramPostSearchEngine (channels.searchPosts: hashtag & text query)
    And deposits all candidates into the shared candidate queue ('queue:normal').
    """
    # Fast mock sleep
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    import scavenger
    monkeypatch.setattr(scavenger, "get_all_keywords", lambda: ["ذهب", "فوركس"])
    monkeypatch.setattr(scavenger, "POPULAR_HASHTAGS", ["ذهب", "فوركس"])
    monkeypatch.setattr(scavenger, "POPULAR_POST_QUERIES", ["XAUUSD BUY"])

    mock_redis = MagicMock()
    mock_redis.llen.return_value = 0 # No backpressure
    mock_redis.sadd.return_value = 1
    mock_redis.incr.return_value = 1
    mock_redis.get.return_value = None

    enqueued_items = []
    mock_redis.rpush.side_effect = lambda queue, val: enqueued_items.append((queue, val))

    mock_tg = MagicMock(spec=TelegramManager)
    
    # 1. Contacts search mock
    mock_contacts_chan = MagicMock(id=101, username="contacts_discovered_chan", broadcast=True, title="Contacts Chan")
    contacts_res = MagicMock(chats=[mock_contacts_chan])
    mock_tg.execute_request = AsyncMock(return_value=contacts_res)

    # 2. Global search mock
    mock_global_chan = MagicMock(id=202, username="global_discovered_chan", broadcast=True, title="Global Chan")
    mock_global_msg = MagicMock(id=1, chat=mock_global_chan, text="XAUUSD BUY #Gold", date=datetime.now(timezone.utc), peer_id=None)
    global_search_res = MagicMock(messages=[mock_global_msg], chats=[mock_global_chan], next_rate=0)
    mock_tg.search_global_messages = AsyncMock(return_value=global_search_res)

    # 3. Post search mock
    mock_post_chan = MagicMock(id=303, username="post_discovered_chan", broadcast=True, title="Post Chan")
    mock_post_msg = MagicMock(id=2, chat=mock_post_chan, text="SMC Strategy #Forex", date=datetime.now(timezone.utc), peer_id=None)
    post_search_res = MagicMock(messages=[mock_post_msg], chats=[mock_post_chan], next_rate=0)
    mock_tg.search_posts = AsyncMock(return_value=post_search_res)

    mock_tg.sleep_adaptive_jitter = AsyncMock()

    chk_mgr = SearchCheckpointManager(mock_redis)
    prov_mgr = ProvenanceManager(mock_redis)

    shutdown_event = asyncio.Event()

    # Call with full explicit parameters
    await run_scavenger(
        tg_manager=mock_tg,
        redis_conn=mock_redis,
        session_name="scavenger_session",
        shutdown_event=shutdown_event,
        checkpoint_mgr=chk_mgr,
        provenance_mgr=prov_mgr,
        candidate_queue="queue:normal"
    )

    # Verify that ALL THREE discovery sources were invoked
    assert mock_tg.execute_request.called, "Source 1 (Contacts directory search) must be executed"
    assert mock_tg.search_global_messages.called, "Source 2 (Global message search) must be executed"
    assert mock_tg.search_posts.called, "Source 3 (Public channel post search) must be executed"

    # Verify that all candidates were enqueued to the shared queue:normal
    assert len(enqueued_items) >= 3
    for queue_name, handle in enqueued_items:
        assert queue_name == "queue:normal"

    enqueued_handles = [item[1] for item in enqueued_items]
    assert "contacts_discovered_chan" in enqueued_handles
    assert "global_discovered_chan" in enqueued_handles
    assert "post_discovered_chan" in enqueued_handles

    print("All 3 discovery sources successfully executed into shared candidate queue!")


@pytest.mark.asyncio
async def test_scavenger_signature_flexibility_and_defaults():
    """
    Proves that run_scavenger works with minimal positional/default arguments
    without requiring external managers or explicit candidate queues.
    """
    mock_redis = MagicMock()
    mock_redis.llen.return_value = 0
    mock_redis.sadd.return_value = 1
    mock_redis.incr.return_value = 1
    mock_redis.get.return_value = None

    mock_tg = MagicMock(spec=TelegramManager)
    mock_tg.execute_request = AsyncMock(return_value=None)
    mock_tg.search_global_messages = AsyncMock(return_value=None)
    mock_tg.search_posts = AsyncMock(return_value=None)
    mock_tg.sleep_adaptive_jitter = AsyncMock()

    shutdown_event = asyncio.Event()
    shutdown_event.set() # Stop immediately

    # Call with minimal default signature: run_scavenger(tg_manager, redis_conn, session_name, shutdown_event)
    result = await run_scavenger(
        mock_tg,
        mock_redis,
        "scavenger_session",
        shutdown_event
    )
    assert result == 0

