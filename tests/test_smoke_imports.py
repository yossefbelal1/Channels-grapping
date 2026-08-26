"""
tests/test_smoke_imports.py — Smoke tests ensuring all critical application modules import cleanly
"""

import unittest


class TestSmokeImports(unittest.TestCase):

    def test_import_core_modules(self):
        import tg_manager
        import validator
        import campaign_worker
        import seed_intake_worker
        import graph_expander
        import scavenger
        import radar
        import dashboard
        self.assertIsNotNone(tg_manager.TelegramManager)
        self.assertIsNotNone(validator.LeadValidator)
        self.assertIsNotNone(dashboard.app)

    def test_import_app_package_modules(self):
        import app.core.config
        import app.core.db
        import app.core.redis_client
        import app.repositories.lead_repository
        import app.repositories.campaign_repository
        import app.validator.link_parser
        import app.validator.contact_extractor
        import app.validator.scoring
        self.assertIsNotNone(app.core.db.get_db_pool)
        self.assertIsNotNone(app.repositories.lead_repository.LeadRepository)


if __name__ == '__main__':
    unittest.main()
