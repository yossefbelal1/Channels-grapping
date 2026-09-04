import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.graph.edge_manager import EdgeRelation
from app.graph.forward_analyzer import ForwardAnalyzer
from graph_expander import GraphExpander

@pytest.fixture
def mock_expander():
    expander = GraphExpander()
    expander.tg_manager = AsyncMock()
    expander.edge_mgr = MagicMock()
    expander.provenance_mgr = MagicMock()
    expander.provenance_mgr.record_candidate_discovery.return_value = (True, 1, ["graph"])
    expander.redis_conn = MagicMock()
    expander.db_helper = MagicMock()
    expander.session_name = "test_session"
    return expander

def test_forward_extraction():
    class MockPeer:
        channel_id = 123456789

    class MockFwd:
        from_id = MockPeer()
        from_name = "test_signal_provider"

    class MockMsg:
        fwd_from = MockFwd()

    origin = ForwardAnalyzer.extract_forward_origin(MockMsg())
    assert origin is not None
    assert origin["is_forward"] is True
    assert origin["channel_id"] == "123456789"
    assert origin["from_name"] == "test_signal_provider"

@pytest.mark.asyncio
async def test_expand_entity_recommendations_and_forwards(mock_expander):
    # Mock row
    row = {
        'id': 'source-uuid',
        'channel_username': 'source_channel',
        'lead_score': 85,
        'depth': 0
    }

    # Mock entity
    mock_entity = MagicMock()
    mock_entity.broadcast = True
    mock_entity.username = 'source_channel'
    mock_expander.tg_manager.execute_request.return_value = mock_entity

    # Mock fetch_posts
    mock_expander.fetch_posts = AsyncMock()
    
    # Create fake messages
    class MockMsg:
        def __init__(self, text, fwd=None):
            self.message = text
            self.fwd_from = fwd
            self.id = 1
    
    class MockFwd:
        from_name = "fwd_channel"
        from_id = None
    
    msg_fwd = MockMsg("Forwarded signal", fwd=MockFwd())
    msg_link = MockMsg("Check out t.me/linked_channel")
    msg_mention = MockMsg("Shoutout to @mention_channel")
    msg_promo = MockMsg("إعلان t.me/promo_channel")

    mock_expander.fetch_posts.return_value = [msg_fwd, msg_link, msg_mention, msg_promo]

    # Mock recommendations
    class MockRecs:
        class MockChat:
            username = "rec_channel"
        chats = [MockChat()]
    
    mock_expander.tg_manager.get_channel_recommendations.return_value = MockRecs()
    mock_expander.insert_or_get_target_lead = MagicMock(side_effect=lambda u, d, s: f"target-uuid-{u}")

    # Run expand_entity
    await mock_expander.expand_entity(row)

    # Verify edge creations
    calls = mock_expander.edge_mgr.record_edge.call_args_list
    relations = [c.kwargs.get('relation_type') or c.args[2] for c in calls]
    
    assert EdgeRelation.FORWARDED_FROM in relations
    assert EdgeRelation.LINKED in relations
    assert EdgeRelation.PROMOTED in relations
    assert EdgeRelation.MENTION in relations
    assert EdgeRelation.RECOMMENDATION in relations

    # Verify unique deduplication via provenance manager check
    assert mock_expander.provenance_mgr.record_candidate_discovery.call_count == 5
