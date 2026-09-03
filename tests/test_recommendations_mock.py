"""
tests/test_recommendations_mock.py — Mocked Unit Tests for Similar Channel Recommendations
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from tg_manager import TelegramManager
from app.graph.edge_manager import GraphEdgeManager, EdgeRelation


@pytest.mark.asyncio
async def test_get_channel_recommendations_graph_expansion():
    mock_redis = MagicMock()
    
    mock_rec_channel_1 = MagicMock()
    mock_rec_channel_1.id = 111111
    mock_rec_channel_1.title = "Arabic Scalping FX"
    mock_rec_channel_1.username = "arabic_scalping_fx"

    mock_rec_channel_2 = MagicMock()
    mock_rec_channel_2.id = 222222
    mock_rec_channel_2.title = "Gold Signals VIP"
    mock_rec_channel_2.username = "gold_signals_vip"

    mock_result = MagicMock()
    mock_result.chats = [mock_rec_channel_1, mock_rec_channel_2]

    with patch.object(TelegramManager, 'execute_request', new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_result
        
        tg = TelegramManager(redis_conn=mock_redis)
        res = await tg.get_channel_recommendations(channel_peer="main_trading_hub")

        assert res is not None
        assert len(res.chats) == 2
        assert res.chats[0].username == "arabic_scalping_fx"
        assert res.chats[1].username == "gold_signals_vip"
