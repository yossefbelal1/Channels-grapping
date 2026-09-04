"""
End-to-End Simulation Pipeline Test:
Discovery -> Provenance -> Stage 1 -> Deep Validation -> Multi-Dimensional Scoring -> Graph Edges -> Dynamic Scheduling
"""

from unittest.mock import MagicMock
from datetime import datetime, timezone
import pytest

from app.discovery.provenance import ProvenanceManager
from app.discovery.taxonomy import classify_text_taxonomy
from app.scoring.engine import LeadScoringEngine
from app.graph.edge_manager import GraphEdgeManager, EdgeRelation
from app.graph.forward_analyzer import ForwardAnalyzer
from app.scheduler.activity_classifier import ActivityClassifier
from app.validator.contact_extractor import extract_contacts


def test_full_discovery_pipeline_simulation():
    # ── 1. Redis & DB Mock Setup ──
    mock_redis = MagicMock()
    mock_redis.sadd.return_value = 1
    mock_redis.incr.return_value = 1
    mock_redis.smembers.return_value = {b"global_search"}

    mock_db_conn = MagicMock()
    mock_cur = MagicMock()
    mock_db_conn.cursor.return_value.__enter__.return_value = mock_cur

    # ── 2. Candidate Discovery Signal ──
    raw_link = "https://t.me/NicheGoldTrader_Arab"
    prov_mgr = ProvenanceManager(redis_conn=mock_redis, db_conn=mock_db_conn)
    is_new, count, sources = prov_mgr.record_candidate_discovery(
        username_or_link=raw_link,
        source_type="global_search",
        keyword="توصيات الذهب"
    )
    assert is_new is True
    assert count == 1

    # ── 3. Stage 1 Cheap Validation ──
    channel_title = "نادي متداولي الذهب والعملات"
    channel_bio = "صفقات يومية سكالبينج وتحليل فني على الذهب XAUUSD. للإدارة: @GoldMasterAdmin واتساب: https://wa.me/201207500631"
    
    stage1_pass, reason, prelim_score = LeadScoringEngine.evaluate_stage_1(
        title=channel_title,
        description=channel_bio,
        username="nichegoldtrader_arab",
        member_count=220 # Small channel
    )
    assert stage1_pass is True

    # ── 4. Stage 2 Deep Validation & Message Sampling ──
    sample_posts = [
        "صفقة شراء فوركس XAUUSD الدخول 2640 الهدف 2670 وقف الخسارة 2625",
        "تحديث السوق: اختراق مناطق العرض والطلب بنجاح ووصول الهدف الثاني +60 نقطة",
        "تحليل العملات الرقمية والذهب الأسبوعي برعاية وسيط مرخص ECN"
    ]

    contacts = extract_contacts(text=" ".join(sample_posts), description=channel_bio, channel_username="nichegoldtrader_arab")
    assert contacts["admin_username"] == "GoldMasterAdmin"
    assert contacts["whatsapp"] == "201207500631"

    scores = LeadScoringEngine.evaluate_stage_2(
        title=channel_title,
        description=channel_bio,
        recent_posts=sample_posts,
        member_count=220,
        has_contact=True,
        contact_types=[c["type"] for c in contacts["structured_contacts"]],
        posts_24h=2,
        posts_7d=10,
        posts_30d=35,
        last_post_at=datetime.now(timezone.utc)
    )

    # ── 5. Verify Scoring Engine Quality ──
    assert scores.gold_score >= 40
    assert scores.signal_score >= 30
    assert scores.final_score >= 50
    assert scores.classification in ["HIGH_CONFIDENCE_FOREX", "LIKELY_FOREX"]

    # ── 6. Activity Classification & Crawl Scheduling ──
    act_class, interval, next_crawl = ActivityClassifier.classify_activity(
        posts_24h=2,
        posts_7d=10,
        posts_30d=35,
        last_post_at=datetime.now(timezone.utc)
    )
    assert act_class == "WARM"
    assert next_crawl is not None

    # ── 7. Multi-Edge Graph Extraction ──
    edge_mgr = GraphEdgeManager(db_conn=mock_db_conn, redis_conn=mock_redis)
    edge_mgr.record_edge(
        source_channel_id="11111111-1111-1111-1111-111111111111",
        target_channel_id="22222222-2222-2222-2222-222222222222",
        relation_type=EdgeRelation.FORWARDED_FROM,
        confidence=95,
        evidence="Forwarded trade signal"
    )
    assert mock_cur.execute.called

    print("All E2E discovery pipeline steps passed successfully!")
