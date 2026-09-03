"""
tests/test_global_search_mock.py — Mocked Unit Tests for Telegram Global Message Search
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from tg_manager import TelegramManager
from app.discovery.checkpoint import SearchCheckpointManager
from app.discovery.provenance import ProvenanceManager


@pytest.mark.asyncio
async def test_search_global_messages_content_based_discovery():
    """
    Ensures channels like 'The Market Room' are discovered based purely on post content:
    'XAUUSD BUY 2450 SL 2440 TP 2475'
    """
    mock_redis = MagicMock()
    mock_db = MagicMock()
    
    # Mock Telethon Client
    mock_client = AsyncMock()
    mock_channel = MagicMock()
    mock_channel.id = 123456789
    mock_channel.title = "The Market Room" # Name has zero forex keywords!
    mock_channel.username = "themarketroom_signals"
    mock_channel.broadcast = True

    mock_msg = MagicMock()
    mock_msg.id = 555
    mock_msg.peer_id = MagicMock()
    mock_msg.chat = mock_channel
    mock_msg.text = "XAUUSD BUY 2450 SL 2440 TP 2475 #Gold #Forex"

    mock_result = MagicMock()
    mock_result.messages = [mock_msg]
    mock_result.chats = [mock_channel]

    mock_client.return_value = mock_result

    # Run search_global_messages via TelegramManager
    with patch.object(TelegramManager, 'execute_request', new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_result
        
        tg = TelegramManager(redis_conn=mock_redis)
        res = await tg.search_global_messages(
            query="توصيات الذهب",
            limit=10,
            offset_id=0,
            offset_rate=0
        )

        assert res is not None
        assert len(res.messages) == 1
        assert "XAUUSD BUY" in res.messages[0].text
        assert res.chats[0].username == "themarketroom_signals"


def test_checkpoint_pagination_flow():
    mock_redis = MagicMock()
    mock_db = MagicMock()
    mock_cur = MagicMock()
    mock_db.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchone.return_value = None

    mock_redis.get.return_value = None # No cached checkpoint

    chk_mgr = SearchCheckpointManager(redis_conn=mock_redis, db_conn=mock_db)
    cp = chk_mgr.get_checkpoint(
        search_type="global_search",
        query_key="forex_arabic"
    )

    assert cp is None

    # Save progress after fetching page 1
    chk_mgr.save_checkpoint(
        search_type="global_search",
        query_key="forex_arabic",
        offset_id=555,
        offset_rate=12345,
        page_number=1,
        total_yield=10,
        status="active"
    )

    assert mock_cur.execute.called
    assert mock_redis.set.called
