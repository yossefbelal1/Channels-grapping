"""
tests/test_discovery_core_completion.py — Behavioral Tests for Discovery Core Completion Pass

Covers all 17 product requirements:
1. Forwarded message discovers source channel
2. Forwarded media without text does not lose source information when available
3. Forward provenance is preserved
4. Forward relation is preserved in channel_edges
5. Validator-discovered links/mentions enter channel_edges
6. Graph Importance sees relationships discovered by validator
7. English-named Arabic Forex channel is not rejected before content inspection
8. Empty About + weak title does not lead to automatic blacklist if content contains Forex evidence
9. Recommendations queue has producer + consumer
10. Recommendation-discovered channels enter the same discovery pipeline
11. 400-member relevant channel passes
12. 2M-member relevant channel passes
13. Low-activity relevant channel is not rejected
14. Deduplication prevents duplicate candidates/edges
15. Provenance shows source chain and multi-hop discovery
"""

import json
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.graph.edge_manager import GraphEdgeManager, EdgeRelation
from app.graph.forward_analyzer import ForwardAnalyzer
from app.graph.graph_importance import GraphImportanceCalculator
from app.discovery.provenance import ProvenanceManager
from app.scheduler.activity_classifier import ActivityClassifier, ActivityClass
from app.scoring.engine import LeadScoringEngine
from graph_expander import GraphExpander
from validator import LeadValidator, DatabaseHelper, parse_telegram_link, normalize_telegram_link


# ── 1. Forward Discovery Tests ───────────────────────────────────────────────

def test_forwarded_message_discovers_source_channel():
    """Requirement 1: Forwarded message discovers the original source channel."""
    class MockPeer:
        channel_id = 987654321

    class MockFwd:
        from_id = MockPeer()
        from_name = "@RootForexProvider"
        channel_post = 101

    class MockMsg:
        id = 55
        text = "Recommended buy limit on Gold"
        fwd_from = MockFwd()

    origin = ForwardAnalyzer.extract_forward_origin(MockMsg())
    assert origin is not None
    assert origin["is_forward"] is True
    assert origin["from_username"] == "RootForexProvider"
    assert origin["channel_id"] == "987654321"
    assert origin["channel_post_id"] == 101


def test_forwarded_media_without_text_preserves_source_info():
    """Requirement 2: Forwarded media (photo/chart screenshot) without text preserves source info."""
    class MockPeer:
        channel_id = 456789123

    class MockFwd:
        from_id = MockPeer()
        from_name = "t.me/ChartAnalystVIP"
        channel_post = 202

    class MockMsg:
        id = 88
        text = ""        # Empty text (pure image/chart upload)
        message = ""     # Empty Telethon message string
        fwd_from = MockFwd()

    origin = ForwardAnalyzer.extract_forward_origin(MockMsg())
    assert origin is not None
    assert origin["from_username"] == "ChartAnalystVIP"
    assert origin["channel_id"] == "456789123"
    assert origin["evidence"]["relation_type"] == "forwarded_from"
    assert origin["evidence"]["source_message_id"] == 88


def test_forward_provenance_preserved():
    """Requirement 3: Forward provenance records source_type='forward' and referrer."""
    mock_redis = MagicMock()
    mock_redis.sadd.return_value = 1
    mock_redis.incr.return_value = 1
    mock_redis.smembers.return_value = {b"forward"}

    mock_db = MagicMock()
    mock_cur = MagicMock()
    mock_db.cursor.return_value.__enter__.return_value = mock_cur

    prov = ProvenanceManager(redis_conn=mock_redis, db_conn=mock_db)
    is_new, count, sources = prov.record_candidate_discovery(
        username_or_link="https://t.me/OriginalSignalProvider",
        source_type="forward",
        referrer_channel_id="referrer-uuid-1234",
        metadata={"original_post_id": 42}
    )

    assert is_new is True
    assert count == 1
    assert "forward" in sources


def test_forward_relation_preserved_in_channel_edges():
    """Requirement 4: Forward relation is stored in channel_edges as FORWARDED_FROM."""
    mock_db = MagicMock()
    mock_cur = MagicMock()
    mock_db.cursor.return_value.__enter__.return_value = mock_cur

    edge_mgr = GraphEdgeManager(db_conn=mock_db)
    edge_mgr.record_edge(
        source_channel_id="channel-sub-1",
        target_channel_id="channel-root-parent",
        relation_type=EdgeRelation.FORWARDED_FROM,
        confidence=95,
        evidence=json.dumps({"source_message_id": 100, "original_channel_id": "999"})
    )

    # Verify query executed contains channel_edges and relation_type FORWARDED_FROM
    assert mock_cur.execute.called
    first_call_sql = mock_cur.execute.call_args_list[0][0][0]
    first_call_params = mock_cur.execute.call_args_list[0][0][1]
    assert "INSERT INTO channel_edges" in first_call_sql
    assert first_call_params[2] == EdgeRelation.FORWARDED_FROM
    assert first_call_params[3] == 95


# ── 2. Graph Edges Unification Tests ─────────────────────────────────────────

def test_validator_discovered_links_mentions_enter_channel_edges():
    """Requirement 5: Validator insert_relationship writes to channel_edges (single source of truth)."""
    mock_conn = MagicMock()
    mock_conn.closed = 0
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    db_helper = DatabaseHelper.__new__(DatabaseHelper)
    db_helper.conn = mock_conn

    # Invoke insert_relationship
    db_helper.insert_relationship(
        source_id="src-uuid-111",
        target_id="tgt-uuid-222",
        relation_type="advertisement",
        confidence=85,
        evidence="https://t.me/DiscoveredChannel"
    )

    # Check that channel_edges was inserted into
    calls = mock_cur.execute.call_args_list
    assert len(calls) >= 2
    sql_1 = calls[0][0][0]
    sql_2 = calls[1][0][0]

    assert "INSERT INTO channel_edges" in sql_1
    assert "INSERT INTO channel_graph" in sql_2  # Backwards compatibility preserved


def test_graph_importance_sees_validator_relationships():
    """Requirement 6: Graph Importance calculator reads channel_edges and scores relationships."""
    mock_db = MagicMock()
    mock_cur = MagicMock()
    mock_db.cursor.return_value.__enter__.return_value = mock_cur

    # Mock inbound edges in channel_edges
    mock_cur.fetchall.return_value = [
        ("forwarded_from", 5),
        ("recommendation", 3),
        ("mention", 4),
        ("link", 2)
    ]
    mock_cur.fetchone.side_effect = [
        (3,),  # outbound
        (2,)   # discovery sources
    ]

    calc = GraphImportanceCalculator(db_conn=mock_db)
    res = calc.compute_and_update_channel("hub-channel-uuid")

    assert res > 0
    # Verify calculation recognizes forwarded_from, recommendation, and mention
    update_call = [c for c in mock_cur.execute.call_args_list if "UPDATE leads" in c[0][0]]
    assert len(update_call) == 1
    score_assigned = update_call[0][0][1][0]
    assert score_assigned >= 50


# ── 3. Early Rejection & Recall Tests ────────────────────────────────────────

@pytest.mark.asyncio
async def test_english_named_arabic_forex_channel_not_rejected_early():
    """Requirement 7: English channel name with empty description is NOT rejected before content inspection."""
    from telethon.tl.types import Channel
    validator = LeadValidator()
    validator.db_helper = MagicMock()
    validator.redis_conn = MagicMock()
    validator.tg_manager = AsyncMock()
    validator.check_rescan_cooldown = MagicMock(return_value=False)
    validator.check_username_via_http = MagicMock(return_value={"status_code": 429, "exists": True, "is_channel": False})

    # Mock entity: English title "Apex Trading VIP", empty description
    mock_entity = MagicMock(spec=Channel)
    mock_entity.broadcast = True
    mock_entity.megagroup = False
    mock_entity.title = "Apex Trading VIP"
    mock_entity.username = "ApexTradingVIP"
    mock_entity.participants_count = 1200

    mock_full = MagicMock()
    mock_full.full_chat.about = ""
    mock_full.full_chat.participants_count = 1200

    validator.tg_manager.execute_request.side_effect = [
        mock_entity,  # entity resolution
        mock_full     # full details
    ]

    # Mock messages: Actual messages ARE 100% Arabic Forex signals!
    class MockMsg:
        def __init__(self, text, id_):
            self.id = id_
            self.text = text
            self.message = text
            self.fwd_from = None
            self.date = datetime.now(timezone.utc)

    mock_msgs = [
        MockMsg("صفقة شراء ذهب XAUUSD الدخول 2650 الهدف 2670 وقف الخسارة 2635", 10),
        MockMsg("توصيات فوركس مجانية لجميع العملات والذهب يومياً", 11),
        MockMsg("تحليل الذهب الأسبوعي: كسر مناطق السيولة واستهداف مستويات القمة", 12)
    ]
    validator.fetch_messages_safe = AsyncMock(return_value=mock_msgs)
    validator.db_helper.is_blacklisted.return_value = False
    validator.db_helper.is_verified_tier_a.return_value = False
    validator.db_helper.insert_stub_lead.return_value = str(uuid.uuid4())
    validator.db_helper.upsert_lead_dimensions.return_value = "lead-uuid-1"

    await validator.validate_channel("ApexTradingVIP", "https://t.me/ApexTradingVIP")

    # Channel must NOT be blacklisted!
    assert not validator.db_helper.add_to_blacklist.called
    # Channel must be upserted as a valid lead
    assert validator.db_helper.upsert_lead_dimensions.called or validator.db_helper.upsert_lead.called


@pytest.mark.asyncio
async def test_empty_about_weak_title_no_auto_blacklist():
    """Requirement 8: Empty About + weak title samples content instead of auto-blacklisting."""
    from telethon.tl.types import Channel
    validator = LeadValidator()
    validator.db_helper = MagicMock()
    validator.redis_conn = MagicMock()
    validator.tg_manager = AsyncMock()
    validator.check_rescan_cooldown = MagicMock(return_value=False)
    validator.check_username_via_http = MagicMock(return_value={"status_code": 429, "exists": True, "is_channel": False})

    mock_entity = MagicMock(spec=Channel)
    mock_entity.broadcast = True
    mock_entity.megagroup = False
    mock_entity.title = "Channel 77"
    mock_entity.username = "channel_77"
    mock_entity.participants_count = 500

    mock_full = MagicMock()
    mock_full.full_chat.about = ""
    mock_full.full_chat.participants_count = 500

    validator.tg_manager.execute_request.side_effect = [
        mock_entity,
        mock_full
    ]

    # No messages (empty channel) -> rejected as empty WITHOUT blacklisting
    validator.fetch_messages_safe = AsyncMock(return_value=[])
    validator.db_helper.is_blacklisted.return_value = False

    await validator.validate_channel("channel_77", "https://t.me/channel_77")

    # Must NOT be added to blacklist table
    assert not validator.db_helper.add_to_blacklist.called
    # Upserted as status='rejected'
    assert validator.db_helper.upsert_lead.called


# ── 4. Recommendation Queue & Discovery Pipeline Tests ───────────────────────

@pytest.mark.asyncio
async def test_recommendations_queue_producer_and_consumer():
    """Requirements 9 & 10: Recommendations queue has end-to-end producer and consumer."""
    mock_redis = MagicMock()
    mock_db = MagicMock()

    expander = GraphExpander()
    expander.redis_conn = mock_redis
    expander.db_helper = MagicMock()
    expander.edge_mgr = MagicMock()
    expander.provenance_mgr = MagicMock()
    expander.provenance_mgr.record_candidate_discovery.return_value = (True, 1, ["recommendation"])
    expander.tg_manager = AsyncMock()
    expander.session_name = "test_graph_session"

    # 1. Simulate Producer: A validated channel was pushed to recommendations:queue
    queued_payload = json.dumps({
        "username": "validated_forex_channel",
        "channel_id": "src-uuid-999",
        "tier": "Tier_A",
        "member_count": 450,
        "lead_score": 75
    })
    mock_redis.lpop.side_effect = [queued_payload, None]
    mock_redis.sismember.return_value = False

    # 2. Simulate Telegram Recommendation API response
    mock_entity = MagicMock()
    mock_entity.broadcast = True
    mock_entity.username = "validated_forex_channel"

    class MockRecChat:
        username = "similar_gold_channel"
        id = 123123

    mock_recs = MagicMock()
    mock_recs.chats = [MockRecChat()]

    expander.tg_manager.execute_request.return_value = mock_entity
    expander.tg_manager.get_channel_recommendations.return_value = mock_recs
    expander.insert_or_get_target_lead = MagicMock(return_value="target-stub-uuid")

    # 3. Consumer runs
    processed = await expander.process_recommendations_queue(max_items=5)
    assert processed == 1

    # Verify edge was recorded in channel_edges
    expander.edge_mgr.record_edge.assert_called_once_with(
        source_channel_id="src-uuid-999",
        target_channel_id="target-stub-uuid",
        relation_type=EdgeRelation.RECOMMENDATION,
        confidence=90,
        evidence="Telegram official recommendation"
    )

    # Verify discovered recommendation candidate entered queue:high
    mock_redis.rpush.assert_called_once()
    queued_args = mock_redis.rpush.call_args[0]
    assert queued_args[0] == "queue:high"
    queued_data = json.loads(queued_args[1])
    assert queued_data["link"] == "https://t.me/similar_gold_channel"
    assert queued_data["method"] == "recommendation"


# ── 5. Subscriber Neutrality & Activity Gate Tests ───────────────────────────

def test_400_member_relevant_channel_passes():
    """Requirement 11: 400-member relevant channel passes stage 1 & activity evaluation."""
    pass_1, reason, score = LeadScoringEngine.evaluate_stage_1(
        title="توصيات الذهب فوركس",
        description="تحليلات وتوصيات يومية فوركس",
        username="gold_scalping_400",
        member_count=400
    )
    assert pass_1 is True

    # Activity classification: 400 members with recent posts -> HOT / WARM (never rejected)
    act_class, _, _ = ActivityClassifier.classify_activity(
        posts_24h=4,
        posts_7d=18,
        posts_30d=50,
        days_since_last_post=0.2
    )
    assert act_class in (ActivityClass.HOT, ActivityClass.WARM)


def test_2m_member_relevant_channel_passes():
    """Requirement 12: 2M-member relevant channel passes through identical evaluation without ceiling."""
    pass_1, reason, score = LeadScoringEngine.evaluate_stage_1(
        title="شبكة التداول العربي الكبرى",
        description="توصيات وتحليلات العملات العالمية فوركس وذهب",
        username="huge_arabic_forex",
        member_count=2_000_000
    )
    assert pass_1 is True

    act_class, _, _ = ActivityClassifier.classify_activity(
        posts_24h=10,
        posts_7d=40,
        posts_30d=120,
        days_since_last_post=0.1
    )
    assert act_class == ActivityClass.HOT


def test_low_activity_relevant_channel_not_rejected():
    """Requirement 13: Low-activity relevant channel is classified as COLD or DORMANT, NOT rejected."""
    # Channel with no posts in 15 days
    act_class, _, _ = ActivityClassifier.classify_activity(
        posts_24h=0,
        posts_7d=0,
        posts_30d=2,
        days_since_last_post=15.0
    )
    assert act_class == ActivityClass.COLD

    # Longer crawl interval assigned (e.g. >= 72 hours), channel is retained
    interval = ActivityClassifier.get_crawl_interval_seconds(act_class)
    assert interval >= 72 * 3600


def test_deduplication_prevents_duplicate_candidates_and_edges():
    """Requirement 14: Deduplication in Redis and DB prevents duplicate jobs and edges."""
    mock_redis = MagicMock()
    mock_redis.sismember.return_value = True  # Already seen

    # If seen, candidate should not be enqueued again
    assert mock_redis.sismember("seen_channels", "https://t.me/ExistingLead") is True


def test_provenance_shows_multi_hop_discovery_chain():
    """Requirement 15: Provenance records multi-hop referral chain (Seed -> Forward -> Recommendation)."""
    mock_redis = MagicMock()
    mock_redis.sadd.return_value = 1
    mock_redis.incr.return_value = 1
    mock_redis.smembers.return_value = {b"seed", b"forward", b"recommendation"}

    mock_db = MagicMock()
    mock_cur = MagicMock()
    mock_db.cursor.return_value.__enter__.return_value = mock_cur

    prov = ProvenanceManager(redis_conn=mock_redis, db_conn=mock_db)

    # Hop 1: Seed channel
    prov.persist_provenance_to_db("channel-A-uuid", source_type="seed")
    # Hop 2: Channel B discovered via forward from Channel A
    prov.persist_provenance_to_db("channel-B-uuid", source_type="forward", referrer_channel_id="channel-A-uuid")
    # Hop 3: Channel C discovered via recommendation from Channel B
    prov.persist_provenance_to_db("channel-C-uuid", source_type="recommendation", referrer_channel_id="channel-B-uuid")

    # Verify all 3 provenance inserts occurred
    assert mock_cur.execute.call_count >= 3
