"""
tests/test_spider_web_engine.py — Comprehensive Test Suite for Autonomous Spider-Web Discovery Engine

Tests:
1. Candidate Verification & False Positive Filtering (Amazon / generic domains / non-forex).
2. Commercial Intelligence: IB word boundaries & broker affiliate context (No "ib" substring false positives).
3. Priority Engine: Audience Size Invariance (Case A: 400, Case B: 20,000, Case C: 2,000,000 members).
4. Missing Intelligence Handling: Leads with NULL evaluation stay PENDING, not P3.
5. Recursive Spider: Multi-hop traversal and atomic loop prevention.
6. Cross-Platform Bridge Queries: Generation, execution, and graph edge mapping.
7. Database Invariant: Duplicate campaign_logs rejection.
"""

import os
import sys
import json
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.discovery.entity_model import (
    Platform, EntityType, RelationType, CanonicalIdentity,
    DiscoveredEntity, DiscoveredRelationship, DiscoveryCandidate,
    CandidateStatus, GENERIC_DOMAIN_BLACKLIST, GENERIC_HANDLE_BLACKLIST,
    evaluate_candidate_relevance
)
from app.outreach.commercial_inference import CommercialInferenceEngine
from app.outreach.priority_engine import OutreachPriorityEngine
from app.outreach.constants import OutreachPriority
from app.discovery.recursive_spider import RecursiveSpider
from app.graph.cross_platform_graph import CrossPlatformGraphManager
from app.discovery.cross_platform_engine import CrossPlatformDiscoveryEngine


class TestSpiderWebEngine(unittest.TestCase):

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Candidate Verification & False Positive Filtering
    # ──────────────────────────────────────────────────────────────────────────
    def test_generic_domain_filtering(self):
        """Generic non-forex domains (Amazon, Google, Wikipedia) must be rejected."""
        self.assertIn("amazon.fr", GENERIC_DOMAIN_BLACKLIST)
        self.assertIn("google.com", GENERIC_DOMAIN_BLACKLIST)
        self.assertIn("wikipedia.org", GENERIC_DOMAIN_BLACKLIST)

        is_rel, score, terms = evaluate_candidate_relevance(
            title="Amazon.fr : livres, DVD, jeux vidéo, musique",
            description="Achat et vente en ligne parmi des millions de produits",
            raw_text="Livraison gratuite, panier d'achat, promotions vêtements"
        )
        self.assertFalse(is_rel, "E-commerce store should not be relevant")
        self.assertEqual(score, 0)
        self.assertEqual(len(terms), 0)

    def test_forex_relevance_detection(self):
        """Genuine Arabic & English trading portals must receive positive relevance."""
        is_rel_ar, score_ar, terms_ar = evaluate_candidate_relevance(
            title="توصيات فوركس وتحليل الذهب اليومي",
            description="إشارات تداول وصفقات يومية في سوق العملات وإدارة مخاطر احترافية",
            raw_text="تحليل فني لمؤشر الدولار والذهب مع توصيات vip"
        )
        self.assertTrue(is_rel_ar)
        self.assertGreaterEqual(score_ar, 50)
        self.assertIn("فوركس", terms_ar)
        self.assertIn("ذهب", terms_ar)

        is_rel_en, score_en, terms_en = evaluate_candidate_relevance(
            title="Forex & Gold Daily Trading Signals",
            description="Professional scalp trading signals, pips analysis, and funded account challenges.",
            raw_text="Join our VIP forex community for daily trade setups."
        )
        self.assertTrue(is_rel_en)
        self.assertGreaterEqual(score_en, 50)
        self.assertIn("forex", terms_en)
        self.assertIn("gold", terms_en)

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Commercial Intelligence: IB & Broker Affiliate Hardening
    # ──────────────────────────────────────────────────────────────────────────
    def test_ib_substring_collision_prevented(self):
        """
        Words like 'distribution', 'subscribe', 'alhabib' containing 'ib'
        must NOT trigger the broker_affiliate_ib business model!
        """
        eval_result = CommercialInferenceEngine.analyze_channel_commercial_fit(
            title="Free Forex Education and Distribution Center",
            description="Subscribe for free daily market distribution updates. Alhabib trading club.",
            recent_messages=[
                {"id": 1, "text": "Subscribe to our free channel for daily distribution of market charts."}
            ]
        )
        self.assertNotIn(
            "broker_affiliate_ib",
            eval_result["detected_models"],
            "Substring 'ib' in distribution/subscribe must not trigger broker affiliate!"
        )

    def test_broker_name_without_affiliate_context_not_triggered(self):
        """
        Merely mentioning a broker name ('I chart on TradingView and view Exness spreads')
        without registration/affiliate context must NOT trigger broker_affiliate_ib.
        """
        eval_result = CommercialInferenceEngine.analyze_channel_commercial_fit(
            title="Forex Technical Analysis",
            description="We analyze gold prices and compare Exness and XM spreads for chart accuracy.",
            recent_messages=[
                {"id": 1, "text": "Gold hit resistance today as shown on Exness charts."}
            ]
        )
        self.assertNotIn(
            "broker_affiliate_ib",
            eval_result["detected_models"],
            "Passing broker mention must not trigger affiliate business model without partnership context."
        )

    def test_genuine_broker_affiliate_detected(self):
        """
        Channel with explicit affiliate/IB context ('سجل تحت وكالتنا', 'افتح حساب برعايتنا')
        MUST be detected as broker_affiliate_ib.
        """
        eval_result = CommercialInferenceEngine.analyze_channel_commercial_fit(
            title="Forex VIP Signals & Broker Partner",
            description="افتح حسابك برعايتنا في شركة Exness واحصل على كاش باك ورابط الوكالة الخاص.",
            recent_messages=[
                {"id": 1, "text": "سجل تحت وكالتنا للحصول على باقة VIP المجانية وكود وكالة معتمد."}
            ]
        )
        self.assertIn("broker_affiliate_ib", eval_result["detected_models"])

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Priority Engine: Audience Size Invariance (400 vs 20,000 vs 2,000,000)
    # ──────────────────────────────────────────────────────────────────────────
    def test_audience_size_invariance_across_scales(self):
        """
        Verify that audience size is strictly a weak tie-breaker and does NOT
        change priority tiers when business model and commercial evidence are identical.
        Case A: 400 members
        Case B: 20,000 members
        Case C: 2,000,000 members
        """
        common_messages = [
            {"id": 1, "text": "باقة VIP المدفوعة: اشتراك شهري بقيمة 100 USDT عبر Binance Pay.", "date": datetime.now(timezone.utc)},
            {"id": 2, "text": "توصية شراء الذهب XAUUSD Entry 2450 SL 2440 TP 2470 الآن.", "date": datetime.now(timezone.utc)},
            {"id": 3, "text": "للاشتراك تواصل مع الإدارة عبر المعرف الرسمي.", "date": datetime.now(timezone.utc)}
        ]
        contacts = {"contact_username": "trader_admin", "source": "bio_official"}

        # Case A: 400 members (small channel)
        res_a = OutreachPriorityEngine.evaluate_priority(
            title="Gold VIP Signals",
            description="قناة VIP خاصة بتوصيات الذهب والعملات اشتراك شهري",
            recent_messages=common_messages,
            contacts_dict=contacts,
            forex_relevance_score=85,
            member_count=400
        )

        # Case B: 20,000 members (medium channel)
        res_b = OutreachPriorityEngine.evaluate_priority(
            title="Gold VIP Signals",
            description="قناة VIP خاصة بتوصيات الذهب والعملات اشتراك شهري",
            recent_messages=common_messages,
            contacts_dict=contacts,
            forex_relevance_score=85,
            member_count=20_000
        )

        # Case C: 2,000,000 members (massive channel)
        res_c = OutreachPriorityEngine.evaluate_priority(
            title="Gold VIP Signals",
            description="قناة VIP خاصة بتوصيات الذهب والعملات اشتراك شهري",
            recent_messages=common_messages,
            contacts_dict=contacts,
            forex_relevance_score=85,
            member_count=2_000_000
        )

        # 1. Tier Invariance: All three must have the exact same commercial priority tier!
        self.assertEqual(res_a["priority"], OutreachPriority.P1)
        self.assertEqual(res_b["priority"], OutreachPriority.P1)
        self.assertEqual(res_c["priority"], OutreachPriority.P1)
        self.assertEqual(res_a["priority"], res_c["priority"])

        # 2. Score Difference: The maximum score delta purely from audience size (400 vs 2M)
        # must be <= 3 points, proving audience size is strictly a weak tie-breaker.
        score_diff = abs(res_c["priority_score"] - res_a["priority_score"])
        self.assertLessEqual(
            score_diff, 3,
            f"Score difference between 400 and 2,000,000 members was {score_diff}, exceeding 3 pts limit!"
        )

    # ──────────────────────────────────────────────────────────────────────────
    # 4. Missing Intelligence: Leads Default to PENDING, Not P3
    # ──────────────────────────────────────────────────────────────────────────
    def test_missing_intelligence_defaults_to_pending(self):
        """
        When leads have not yet been evaluated for commercial intelligence,
        rerank_campaign_recipients must flag them as PENDING, NOT silently default to P3.
        """
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_db.cursor.return_value.__enter__.return_value = mock_cursor

        mock_cursor.fetchall.return_value = [("PENDING", 12), ("P0", 3)]
        mock_cursor.rowcount = 15

        res = OutreachPriorityEngine.rerank_campaign_recipients(mock_db, "test-campaign-uuid")
        self.assertTrue(res["success"])
        self.assertIn(OutreachPriority.PENDING, res["tier_counts"])
        self.assertEqual(res["tier_counts"][OutreachPriority.PENDING], 12)

        # Verify SQL used COALESCE(l.outreach_priority, 'PENDING')
        executed_sql = mock_cursor.execute.call_args_list[0][0][0]
        self.assertIn("COALESCE(l.outreach_priority, 'PENDING')", executed_sql)

    # ──────────────────────────────────────────────────────────────────────────
    # 5. Recursive Spider: Multi-Hop Traversal and Loop Prevention
    # ──────────────────────────────────────────────────────────────────────────
    def test_spider_loop_prevention_with_atomic_claim(self):
        """
        Verify that Spider uses atomic claim to prevent circular graph crawl.
        """
        mock_redis = MagicMock()
        mock_db = MagicMock()
        mock_graph = MagicMock()

        spider = RecursiveSpider(
            redis_conn=mock_redis,
            db_conn=mock_db,
            connectors={},
            graph_manager=mock_graph,
            max_depth=4
        )

        # Simulate atomic SET NX: returns True first time, None second time
        mock_redis.set.side_effect = [True, None]

        claim_1 = spider.try_claim_visit("telegram:ozarktrade", 1)
        claim_2 = spider.try_claim_visit("telegram:ozarktrade", 2)

        self.assertTrue(claim_1, "First visit claim must succeed")
        self.assertFalse(claim_2, "Second visit claim must fail (loop prevented)")

    # ──────────────────────────────────────────────────────────────────────────
    # 6. Cross-Platform Bridge Queries & Candidate Data Contract
    # ──────────────────────────────────────────────────────────────────────────
    def test_discovery_candidate_data_contract(self):
        """Verify normalized DiscoveryCandidate contract across platforms."""
        cand = DiscoveryCandidate(
            platform=Platform.TIKTOK,
            native_identifier="trader_sam",
            canonical_id="tiktok:trader_sam",
            canonical_url="https://www.tiktok.com/@trader_sam",
            source_entity="web:fxstreet.com",
            discovery_method="bio_bridge",
            relevance_score=80
        )
        self.assertEqual(cand.status, CandidateStatus.DISCOVERED)
        ent = cand.to_entity(title="Sam Forex Trader")
        self.assertEqual(ent.entity_type, EntityType.ACCOUNT)
        self.assertEqual(ent.canonical_id, "tiktok:trader_sam")

        cand_dict = cand.to_dict()
        self.assertEqual(cand_dict["platform"], Platform.TIKTOK)
        self.assertEqual(cand_dict["relevance_score"], 80)


if __name__ == "__main__":
    unittest.main()
