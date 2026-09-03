"""
tests/test_phase1_search_integration.py — Integration Test for Phase 1 Search Pipeline

Demonstrates full flow:
1. Global Search (messages.searchGlobal) -> Result -> Canonical Channel -> Dedupe -> Candidate Queue -> Validation
2. SearchPosts (channels.searchPosts) -> Result -> Canonical Channel -> Dedupe -> Candidate Queue -> Validation
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone

from app.discovery.telegram_global_search import TelegramGlobalSearchEngine
from app.discovery.telegram_post_search import TelegramPostSearchEngine
from app.discovery.provenance import ProvenanceManager
from app.scoring.engine import LeadScoringEngine
from app.validator.contact_extractor import extract_contacts
from tg_manager import TelegramManager


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
async def test_scavenger_production_worker_loop_integration():
    """
    Proves that the real production discovery entrypoint (scavenger.py:run_scavenger)
    invokes TelegramGlobalSearchEngine and TelegramPostSearchEngine, depositing candidates into Redis.
    """
    from scavenger import run_scavenger
    from app.discovery.checkpoint import SearchCheckpointManager

    mock_redis = MagicMock()
    mock_redis.llen.return_value = 0 # No backpressure
    mock_redis.sadd.return_value = 1
    mock_redis.incr.return_value = 1
    mock_redis.get.return_value = None

    enqueued_items = []
    mock_redis.rpush.side_effect = lambda queue, val: enqueued_items.append((queue, val))

    mock_tg = MagicMock(spec=TelegramManager)
    mock_chan = MagicMock(id=999, username="scavenger_prod_chan", broadcast=True, title="Scavenger Prod")
    mock_msg = MagicMock(id=1, chat=mock_chan, text="XAUUSD BUY #Gold", date=datetime.now(timezone.utc))
    search_res = MagicMock(messages=[mock_msg], chats=[mock_chan], next_rate=0)
    
    mock_tg.search_global_messages = AsyncMock(return_value=search_res)
    mock_tg.search_posts = AsyncMock(return_value=search_res)
    mock_tg.get_channel_recommendations = AsyncMock(return_value=None)
    mock_tg.sleep_adaptive_jitter = AsyncMock()

    chk_mgr = SearchCheckpointManager(mock_redis)
    prov_mgr = ProvenanceManager(mock_redis)

    shutdown_event = asyncio.Event()

    # Trigger single cycle with fast shutdown
    async def shutdown_soon():
        await asyncio.sleep(0.1)
        shutdown_event.set()

    asyncio.create_task(shutdown_soon())

    await run_scavenger(
        tg_manager=mock_tg,
        redis_conn=mock_redis,
        checkpoint_mgr=chk_mgr,
        provenance_mgr=prov_mgr,
        session_name="scavenger_session",
        shutdown_event=shutdown_event
    )

    # Verify that run_scavenger successfully invoked search_global_messages and deposited candidate
    assert mock_tg.search_global_messages.called
    assert len(enqueued_items) >= 1
    assert any("scavenger_prod_chan" in str(item[1]) for item in enqueued_items)
    print("Scavenger production loop integration verified!")
