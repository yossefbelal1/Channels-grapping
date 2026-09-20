"""
tests/test_similar_channels_hygiene.py — Unit tests for Similar Channels Forex filtering & Channel Hygiene
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

from graph_expander import (
    GraphExpander,
    RECS_TITLE_BLACKLIST,
    RECS_TITLE_FOREX_SIGNALS
)
from validator import check_is_forex, LeadValidator


# ─────────────────────────────────────────────────────────────────────────────
# 1. Title Filter Sets Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_recs_title_blacklist_coverage():
    """Verify that common non-forex spam terms are in the blacklist."""
    blocked_samples = [
        "pubg", "ببجي", "1xbet", "casino", "كازينو",
        "متجر", "store", "free fire", "fortnite", "netflix"
    ]
    for sample in blocked_samples:
        assert any(bl in sample for bl in RECS_TITLE_BLACKLIST), f"Expected '{sample}' in blacklist"


def test_recs_title_forex_signals_coverage():
    """Verify that core forex trading terms are in the signals list."""
    signal_samples = [
        "forex", "فوركس", "gold", "ذهب", "xauusd",
        "توصيات", "signals", "تداول", "vip", "scalping"
    ]
    for sample in signal_samples:
        assert any(fs in sample for fs in RECS_TITLE_FOREX_SIGNALS), f"Expected '{sample}' in forex signals"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Similar Channels Pre-validation Gate Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_process_recommendations_queue_filters_blacklist():
    """Verify that blacklisted channels (betting, gaming, stores) are SKIPPED."""
    expander = GraphExpander()
    expander.redis_conn = MagicMock()
    expander.tg_manager = AsyncMock()
    expander.edge_mgr = MagicMock()
    expander.provenance_mgr = MagicMock()
    expander.provenance_mgr.record_candidate_discovery.return_value = (True, 1, ["recommendation"])
    expander.insert_or_get_target_lead = MagicMock(return_value="lead-123")
    expander.session_name = "test_session"

    # Queue payload
    expander.redis_conn.lpop.side_effect = [
        json.dumps({"username": "source_forex", "channel_id": "100"}),
        None  # Stop loop
    ]
    expander.redis_conn.sismember.return_value = False

    # Mock source entity
    mock_entity = MagicMock()
    mock_entity.broadcast = True
    expander.tg_manager.execute_request.return_value = mock_entity

    # Mock recommendations returned by Telegram:
    # 1. Betting channel -> Should be SKIPPED
    chat_bet = MagicMock()
    chat_bet.username = "wolf_bet_predictions"
    chat_bet.title = "WOLF BET | ملوك التوقعات 1xbet"

    # 2. Gaming/PUBG channel -> Should be SKIPPED
    chat_pubg = MagicMock()
    chat_pubg.username = "pubg_accounts_shop"
    chat_pubg.title = "متجر شدات ببجي وحسابات"

    # 3. Legitimate Forex channel -> Should be enqueued to queue:high
    chat_forex = MagicMock()
    chat_forex.username = "gold_forex_signals"
    chat_forex.title = "توصيات الذهب فوركس XAUUSD VIP"

    # 4. Unknown niche channel -> Should be enqueued to queue:normal
    chat_neutral = MagicMock()
    chat_neutral.username = "station_x_channel"
    chat_neutral.title = "STATION X | ستيشن اكس"

    mock_recs = MagicMock()
    mock_recs.chats = [chat_bet, chat_pubg, chat_forex, chat_neutral]
    expander.tg_manager.get_channel_recommendations.return_value = mock_recs

    processed = await expander.process_recommendations_queue(max_items=1)
    assert processed == 1

    # Verify what was pushed to Redis
    rpush_calls = expander.redis_conn.rpush.call_args_list
    assert len(rpush_calls) == 2, f"Expected 2 enqueued channels, got {len(rpush_calls)}"

    queues_used = [c.args[0] for c in rpush_calls]
    payloads = [json.loads(c.args[1]) for c in rpush_calls]

    # Forex channel went to queue:high
    assert "queue:high" in queues_used
    forex_payload = [p for p in payloads if "gold_forex_signals" in p["link"]][0]
    assert forex_payload is not None

    # Neutral channel went to queue:normal
    assert "queue:normal" in queues_used
    neutral_payload = [p for p in payloads if "station_x_channel" in p["link"]][0]
    assert neutral_payload is not None

    # Blacklisted channels (wolf_bet, pubg) were NEVER enqueued
    all_links = [p["link"] for p in payloads]
    assert not any("wolf_bet" in l for l in all_links)
    assert not any("pubg" in l for l in all_links)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Absolute Blacklist in check_is_forex Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_check_is_forex_rejects_betting_and_gaming():
    """Verify that check_is_forex rejects betting, stores, and gaming even if forex words exist."""
    # Text contains both forex terms and betting terms
    text_betting = "توصيات فوركس وذهب XAUUSD مع أقوى توقعات ومراهنات 1xbet كازينو وبوكر"
    assert check_is_forex(text_betting) is False

    text_gaming = "فوركس وذهب وشراء شدات ببجي وحسابات فورتنايت رخيصة"
    assert check_is_forex(text_gaming) is False

    text_store = "تداول العملات والذهب مع متجر الكتروني وكوبونات خصم"
    assert check_is_forex(text_store) is False


def test_check_is_forex_accepts_clean_forex():
    """Verify that legitimate forex text passes."""
    text_forex = "قناة توصيات فوركس وتداول الذهب XAUUSD صفقات شراء وبيع مع تحديد الهدف ووقف الخسارة إدارة محافظ"
    assert check_is_forex(text_forex) is True


# ─────────────────────────────────────────────────────────────────────────────
# 4. Channel Hygiene Loop Logic Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_channel_hygiene_protects_admin_channels():
    """Verify that channels where the user is creator or admin are NEVER scheduled for leave."""
    validator = LeadValidator()
    validator.user_client = AsyncMock()
    validator.redis_conn = MagicMock()
    validator.db_helper = MagicMock()
    validator.shutdown_event = MagicMock()
    validator.shutdown_event.is_set.side_effect = [False, True]  # Run 1 cycle

    # Daily leaves key is 0
    validator.redis_conn.get.return_value = "0"

    # Mock dialog 1: Admin channel
    dialog_admin = MagicMock()
    dialog_admin.is_channel = True
    dialog_admin.is_group = False
    dialog_admin.name = "My Admin Channel"
    dialog_admin.entity = MagicMock()
    dialog_admin.entity.creator = True
    dialog_admin.entity.admin_rights = None
    dialog_admin.entity.left = False
    dialog_admin.entity.kicked = False
    dialog_admin.entity.username = "my_admin_channel"

    # Mock dialog 2: Non-admin channel that was already processed in DB
    dialog_stale = MagicMock()
    dialog_stale.is_channel = True
    dialog_stale.is_group = False
    dialog_stale.name = "Old Stale Channel"
    dialog_stale.date = datetime.now(timezone.utc) - timedelta(days=20)
    dialog_stale.entity = MagicMock()
    dialog_stale.entity.creator = False
    dialog_stale.entity.admin_rights = None
    dialog_stale.entity.left = False
    dialog_stale.entity.kicked = False
    dialog_stale.entity.username = "old_stale_channel"

    validator.user_client.get_dialogs.side_effect = [
        [dialog_admin, dialog_stale],  # active
        []                              # archived
    ]

    # Mock DB returns 'validated' for old_stale_channel
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = ("validated",)
    mock_cursor_ctx = MagicMock()
    mock_cursor_ctx.__enter__.return_value = mock_cursor
    mock_cursor_ctx.__exit__.return_value = None
    validator.db_helper.conn.cursor.return_value = mock_cursor_ctx

    # Patch asyncio.sleep to avoid waiting during test
    with patch("asyncio.sleep", new_callable=AsyncMock):
        with patch("asyncio.wait_for", new_callable=AsyncMock):
            validator.shutdown_event.is_set.side_effect = [False, False, True]
            try:
                await validator.channel_hygiene_loop()
            except Exception:
                pass

    # Verify: LeaveChannelRequest was called on old_stale_channel, but NEVER on my_admin_channel
    calls = validator.user_client.call_args_list
    left_entities = [c.args[0].channel for c in calls if hasattr(c.args[0], 'channel')]

    # Admin entity must NEVER be in left entities
    assert dialog_admin.entity not in left_entities
    # Stale entity was targeted for leave
    assert dialog_stale.entity in left_entities
