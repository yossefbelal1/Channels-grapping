"""
tests/test_dashboard_regression.py — Regression tests for Dashboard imports, auth, and media security
"""

import os
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException


class TestDashboardRegression(unittest.TestCase):

    def test_dashboard_imports(self):
        """P0 Regression: Ensure dashboard and all its dependencies import without NameError/ImportError."""
        import dashboard
        self.assertIsNotNone(dashboard.app)

    def test_verify_dashboard_auth_production_failure(self):
        """P0 Regression: Ensure missing API key in production raises 500 error instead of opening dashboard."""
        from dashboard import verify_dashboard_auth
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "DASHBOARD_API_KEY": ""}):
            with self.assertRaises(HTTPException) as ctx:
                verify_dashboard_auth(api_key="any_key")
            self.assertEqual(ctx.exception.status_code, 500)

    def test_verify_dashboard_auth_invalid_key(self):
        """P0 Regression: Ensure invalid API key raises 401 Unauthorized."""
        from dashboard import verify_dashboard_auth
        with patch.dict(os.environ, {"DASHBOARD_API_KEY": "secret123"}):
            with self.assertRaises(HTTPException) as ctx:
                verify_dashboard_auth(api_key="wrong_key")
            self.assertEqual(ctx.exception.status_code, 401)

    def test_verify_dashboard_auth_valid_key(self):
        """Ensure valid API key passes authentication."""
        from dashboard import verify_dashboard_auth
        with patch.dict(os.environ, {"DASHBOARD_API_KEY": "secret123"}):
            self.assertTrue(verify_dashboard_auth(api_key="secret123"))

    def test_media_path_traversal_attack(self):
        """P0 Regression: Ensure directory traversal is strictly blocked."""
        from dashboard import sanitize_media_path
        with self.assertRaises(HTTPException) as ctx:
            sanitize_media_path("../../../etc/passwd")
        self.assertEqual(ctx.exception.status_code, 400)

        with self.assertRaises(HTTPException) as ctx:
            sanitize_media_path("/etc/shadow")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_media_path_valid(self):
        """Ensure valid media path inside media directory resolves cleanly."""
        from dashboard import sanitize_media_path
        res = sanitize_media_path("proof_1.jpg")
        self.assertIsNotNone(res)
        self.assertTrue(res.endswith("proof_1.jpg"))


if __name__ == '__main__':
    unittest.main()
