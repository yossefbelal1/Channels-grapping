import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import unittest
from unittest.mock import MagicMock, patch
import json

from app.discovery.entity_model import (
    Platform, EntityType, RelationType,
    CanonicalIdentity, DiscoveredEntity, DiscoveredRelationship
)
from app.discovery.query_generator import QueryGenerator
from app.discovery.connectors.base import BaseDiscoveryConnector, RateLimitPolicy, ConnectorSearchResult
from app.discovery.connectors.tiktok import TikTokDiscoveryConnector
from app.discovery.connectors.facebook import FacebookDiscoveryConnector
from app.discovery.connectors.web import WebDiscoveryConnector
from app.discovery.connectors.telegram import TelegramDiscoveryConnector
from app.graph.cross_platform_graph import CrossPlatformGraphManager
from app.discovery.recursive_spider import RecursiveSpider


class TestCanonicalIdentity(unittest.TestCase):
    def test_canonical_telegram(self):
        self.assertEqual(CanonicalIdentity.generate('telegram', '@forex_signals'), 'telegram:forex_signals')
        self.assertEqual(CanonicalIdentity.generate('telegram', 'https://t.me/gold_trading'), 'telegram:gold_trading')
        self.assertEqual(CanonicalIdentity.generate('telegram', 'Forex_VIP'), 'telegram:forex_vip')

    def test_canonical_tiktok(self):
        self.assertEqual(CanonicalIdentity.generate('tiktok', '@forextrader_arabic'), 'tiktok:forextrader_arabic')
        self.assertEqual(CanonicalIdentity.generate('tiktok', 'https://www.tiktok.com/@crypto_guru?lang=en'), 'tiktok:crypto_guru')

    def test_canonical_facebook(self):
        self.assertEqual(CanonicalIdentity.generate('facebook', 'https://facebook.com/ArabicForexMaster/'), 'facebook:arabicforexmaster')

    def test_canonical_web(self):
        self.assertEqual(CanonicalIdentity.generate('web', 'https://www.forex-signals.com/daily-analysis'), 'web:forex-signals.com/daily-analysis')
        self.assertEqual(CanonicalIdentity.generate('web', 'http://arabictrader.net/news?id=123'), 'web:arabictrader.net/news')


class TestEntityModel(unittest.TestCase):
    def test_discovered_entity_creation(self):
        ent = DiscoveredEntity(
            platform=Platform.TIKTOK,
            entity_type=EntityType.ACCOUNT,
            canonical_id='tiktok:forex_pro',
            username='forex_pro',
            title='Forex Pro TikTok',
            url='https://www.tiktok.com/@forex_pro'
        )
        self.assertEqual(ent.platform, 'tiktok')
        self.assertEqual(ent.canonical_id, 'tiktok:forex_pro')
        d = ent.to_dict()
        self.assertEqual(d['canonical_id'], 'tiktok:forex_pro')
        self.assertEqual(d['platform'], 'tiktok')

    def test_discovered_relationship(self):
        rel = DiscoveredRelationship(
            source_canonical_id='tiktok:forex_pro',
            target_canonical_id='telegram:forex_vip',
            source_platform=Platform.TIKTOK,
            target_platform=Platform.TELEGRAM,
            relation_type=RelationType.LINK,
            confidence=95
        )
        self.assertEqual(rel.relation_type, 'link')
        self.assertEqual(rel.source_platform, 'tiktok')
        self.assertEqual(rel.target_platform, 'telegram')


class TestQueryGenerator(unittest.TestCase):
    def setUp(self):
        self.generator = QueryGenerator()

    def test_platform_operator_generation(self):
        tiktok_queries = self.generator.generate_queries_for_platform(Platform.TIKTOK, limit=5)
        self.assertTrue(len(tiktok_queries) > 0)
        self.assertTrue(any('tiktok.com' in q for q in tiktok_queries))

        fb_queries = self.generator.generate_queries_for_platform(Platform.FACEBOOK, limit=5)
        self.assertTrue(len(fb_queries) > 0)
        self.assertTrue(any('facebook.com' in q for q in fb_queries))

    def test_bridge_queries(self):
        bridge_queries = self.generator.generate_cross_platform_bridge_queries(limit=10)
        self.assertTrue(len(bridge_queries) > 0)
        self.assertTrue(any('t.me' in q for q in bridge_queries))


class DummyConnector(BaseDiscoveryConnector):
    platform = Platform.WEB

    def search(self, query: str, limit: int = 10) -> ConnectorSearchResult:
        return ConnectorSearchResult(query=query, platform=self.platform)


class TestBaseDiscoveryConnector(unittest.TestCase):
    def setUp(self):
        self.connector = DummyConnector(name='test_dummy', platform=Platform.WEB)

    def test_link_extraction(self):
        text = 'Check our Telegram https://t.me/arabic_fx_signals and TikTok https://www.tiktok.com/@trading_expert and FB: https://facebook.com/forexacademy'
        entities, relationships = self.connector.extract_cross_platform_links(
            text=text,
            source_canonical_id='web:mysite.com',
            source_platform=Platform.WEB
        )
        canonical_ids = [e.canonical_id for e in entities]
        self.assertIn('telegram:arabic_fx_signals', canonical_ids)
        self.assertIn('tiktok:trading_expert', canonical_ids)
        self.assertIn('facebook:forexacademy', canonical_ids)

    def test_rate_limiter(self):
        policy = RateLimitPolicy(min_delay_seconds=0.01, max_delay_seconds=0.02)
        connector = DummyConnector(name='rate_test', platform=Platform.WEB, rate_limit_policy=policy)
        self.assertTrue(connector.is_healthy())
        connector.record_failure('rate limit', is_rate_limit=True)
        self.assertFalse(connector.is_healthy())


class TestTikTokConnector(unittest.TestCase):
    def setUp(self):
        self.connector = TikTokDiscoveryConnector()

    @patch.object(TikTokDiscoveryConnector, 'search_public_profiles')
    @patch.object(TikTokDiscoveryConnector, 'fetch_public_url')
    def test_search_extracts_entities(self, mock_fetch, mock_search_profiles):
        mock_search_profiles.return_value = ['forex_arabic_daily']
        mock_fetch.return_value = '<html><head><meta property="og:title" content="Forex Arabic Daily"><meta property="og:description" content="Join our VIP trading channel: https://t.me/arabic_fx_vip"></head></html>'
        res = self.connector.search('forex telegram vip')
        self.assertTrue(len(res.entities) >= 1)
        can_ids = [e.canonical_id for e in res.entities]
        self.assertIn('tiktok:forex_arabic_daily', can_ids)
        self.assertIn('telegram:arabic_fx_vip', can_ids)


class TestFacebookConnector(unittest.TestCase):
    def setUp(self):
        self.connector = FacebookDiscoveryConnector()

    @patch.object(FacebookDiscoveryConnector, 'search_public_pages')
    @patch.object(FacebookDiscoveryConnector, 'fetch_public_url')
    def test_search_extracts_entities(self, mock_fetch, mock_search_pages):
        mock_search_pages.return_value = ['forexsignalsvip']
        mock_fetch.return_value = '<html><head><meta property="og:title" content="Forex Signals VIP Group"><meta property="og:description" content="Best Arabic Forex Analysis: https://t.me/fx_vip_arabic"></head></html>'
        res = self.connector.search('forex signals arabic')
        self.assertTrue(len(res.entities) >= 1)
        can_ids = [e.canonical_id for e in res.entities]
        self.assertIn('facebook:forexsignalsvip', can_ids)
        self.assertIn('telegram:fx_vip_arabic', can_ids)


class TestWebConnector(unittest.TestCase):
    def setUp(self):
        self.connector = WebDiscoveryConnector()

    @patch.object(WebDiscoveryConnector, 'fetch_public_url')
    def test_crawl_website_for_bridges(self, mock_fetch):
        mock_fetch.return_value = '<html><body><h1>Forex Community</h1><a href="https://t.me/forex_arab_community">Join</a><a href="https://tiktok.com/@arab_fx">TikTok</a></body></html>'
        main_ent, relations, cross_ents = self.connector.crawl_website_for_bridges('https://arabicforex.org')
        self.assertIsNotNone(main_ent)
        self.assertEqual(main_ent.canonical_id, 'web:arabicforex.org')
        can_ids = [e.canonical_id for e in cross_ents]
        self.assertIn('telegram:forex_arab_community', can_ids)
        self.assertIn('tiktok:arab_fx', can_ids)


class TestCrossPlatformGraphManager(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_db.cursor.return_value.__enter__.return_value = self.mock_cursor
        self.graph_mgr = CrossPlatformGraphManager(db_conn=self.mock_db)

    def test_ensure_entity_lead(self):
        ent = DiscoveredEntity(
            platform=Platform.TIKTOK,
            entity_type=EntityType.ACCOUNT,
            canonical_id='tiktok:forex_trader',
            username='forex_trader',
            title='Forex Trader',
            url='https://www.tiktok.com/@forex_trader'
        )
        self.mock_cursor.fetchone.return_value = ('00000000-0000-0000-0000-000000000001',)
        lead_id = self.graph_mgr.ensure_entity_lead(ent)
        self.assertEqual(lead_id, '00000000-0000-0000-0000-000000000001')
        self.assertTrue(self.mock_cursor.execute.called)

    def test_record_cross_platform_edge(self):
        rel = DiscoveredRelationship(
            source_canonical_id='tiktok:forex_trader',
            target_canonical_id='telegram:forex_channel',
            source_platform=Platform.TIKTOK,
            target_platform=Platform.TELEGRAM,
            relation_type=RelationType.LINK
        )
        self.mock_cursor.fetchone.side_effect = [
            ('00000000-0000-0000-0000-000000000001',),
            ('00000000-0000-0000-0000-000000000002',)
        ]
        res = self.graph_mgr.record_cross_platform_edge(rel)
        self.assertTrue(res)
        self.assertTrue(self.mock_cursor.execute.called)


class TestRecursiveSpider(unittest.TestCase):
    def setUp(self):
        self.mock_redis = MagicMock()
        self.mock_db = MagicMock()
        self.mock_graph = MagicMock()
        self.mock_connector = MagicMock()
        self.mock_connector.is_healthy.return_value = True

        self.mock_redis.exists.return_value = False
        self.spider = RecursiveSpider(
            redis_conn=self.mock_redis,
            db_conn=self.mock_db,
            connectors={Platform.TIKTOK: self.mock_connector, Platform.WEB: self.mock_connector},
            graph_manager=self.mock_graph,
            max_depth=3,
            budget_per_hop=10
        )

    def test_spider_traversal_cycle(self):
        source_ent = DiscoveredEntity(
            platform=Platform.TIKTOK,
            entity_type=EntityType.ACCOUNT,
            canonical_id='tiktok:alpha_trader',
            username='alpha_trader',
            depth=1
        )
        child_ent = DiscoveredEntity(
            platform=Platform.TELEGRAM,
            entity_type=EntityType.CHANNEL,
            canonical_id='telegram:alpha_signals',
            username='alpha_signals'
        )
        child_rel = DiscoveredRelationship(
            source_canonical_id='tiktok:alpha_trader',
            target_canonical_id='telegram:alpha_signals',
            source_platform=Platform.TIKTOK,
            target_platform=Platform.TELEGRAM,
            relation_type=RelationType.LINK
        )
        self.mock_connector.inspect_public_profile.return_value = (source_ent, [child_rel], [child_ent])

        new_discoveries = self.spider.expand_entity_hop(source_ent)
        self.assertEqual(len(new_discoveries), 1)
        self.assertEqual(new_discoveries[0].canonical_id, 'telegram:alpha_signals')
        self.assertTrue(self.mock_graph.record_cross_platform_edge.called)
        self.assertTrue(self.mock_redis.set.called)

    def test_spider_max_depth_stop(self):
        source_ent = DiscoveredEntity(
            platform=Platform.WEB,
            entity_type=EntityType.WEBSITE,
            canonical_id='web:trading.com',
            depth=4
        )
        new_discoveries = self.spider.expand_entity_hop(source_ent)
        self.assertEqual(len(new_discoveries), 0)


if __name__ == '__main__':
    unittest.main()
