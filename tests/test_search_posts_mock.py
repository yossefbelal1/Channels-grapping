"""
tests/test_search_posts_mock.py — Mocked Unit Tests for Telegram channels.searchPosts
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from tg_manager import TelegramManager


@pytest.mark.asyncio
async def test_search_posts_hashtag_and_keyword_flow():
    mock_redis = MagicMock()
    
    mock_channel = MagicMock()
    mock_channel.id = 987654321
    mock_channel.title = "SMC Trading Hub"
    mock_channel.username = "smc_arabic_traders"
    mock_channel.broadcast = True

    mock_msg = MagicMock()
    mock_msg.id = 101
    mock_msg.text = "تحليل يومي #XAUUSD #SMC مناطق العرض والطلب"
    mock_msg.chat = mock_channel

    mock_result = MagicMock()
    mock_result.messages = [mock_msg]
    mock_result.chats = [mock_channel]

    with patch.object(TelegramManager, 'execute_request', new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_result
        
        tg = TelegramManager(redis_conn=mock_redis)
        res = await tg.search_posts(
            hashtag="#XAUUSD",
            limit=20,
            offset_id=0
        )

        assert res is not None
        assert len(res.messages) == 1
        assert "#SMC" in res.messages[0].text
        assert res.chats[0].username == "smc_arabic_traders"


@pytest.mark.asyncio
async def test_search_posts_graceful_fallback_on_unsupported():
    mock_redis = MagicMock()
    
    with patch.object(TelegramManager, 'execute_request', new_callable=AsyncMock) as mock_exec:
        # Simulate Telegram API error or unsupported channel type
        mock_exec.return_value = None
        
        tg = TelegramManager(redis_conn=mock_redis)
        res = await tg.search_posts(hashtag="#restricted_query")
        
        # System continues without crash
        assert res is None
