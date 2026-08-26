"""
tests/test_dashboard_auth_and_security.py — Complete test suite for Dashboard import, auth, and media security
"""

import os
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi import HTTPException


class TestDashboardAuthAndSecurity(unittest.TestCase):

    def test_dashboard_imports_cleanly(self):
        """P0-A: Ensure dashboard and all its dependencies import without any NameError or ImportError."""
        import dashboard
        self.assertIsNotNone(dashboard.app)

    def test_production_missing_api_key_fails_closed(self):
        """P0-B: When ENVIRONMENT=production and DASHBOARD_API_KEY is missing, requests MUST be rejected (500)."""
        from dashboard import verify_dashboard_auth
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "DASHBOARD_API_KEY": ""}):
            with self.assertRaises(HTTPException) as ctx:
                verify_dashboard_auth(header_key="any_key", query_key=None)
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertIn("DASHBOARD_API_KEY must be configured in production", ctx.exception.detail)

    def test_protected_endpoints_reject_invalid_key(self):
        """P0-B: When key is configured, requests with invalid or missing key must return 401."""
        from dashboard import verify_dashboard_auth
        with patch.dict(os.environ, {"DASHBOARD_API_KEY": "super_secret_123"}):
            # Missing key
            with self.assertRaises(HTTPException) as ctx:
                verify_dashboard_auth(header_key=None, query_key=None)
            self.assertEqual(ctx.exception.status_code, 401)

            # Wrong key
            with self.assertRaises(HTTPException) as ctx:
                verify_dashboard_auth(header_key="wrong_key", query_key=None)
            self.assertEqual(ctx.exception.status_code, 401)

    def test_protected_endpoints_accept_valid_header_key(self):
        """P0-B: Valid X-API-Key header passes authentication."""
        from dashboard import verify_dashboard_auth
        with patch.dict(os.environ, {"DASHBOARD_API_KEY": "super_secret_123"}):
            self.assertTrue(verify_dashboard_auth(header_key="super_secret_123", query_key=None))

    def test_protected_endpoints_accept_valid_query_param_key(self):
        """P0-B: Valid ?api_key= query parameter passes authentication."""
        from dashboard import verify_dashboard_auth
        with patch.dict(os.environ, {"DASHBOARD_API_KEY": "super_secret_123"}):
            self.assertTrue(verify_dashboard_auth(header_key=None, query_key="super_secret_123"))

    def test_media_path_traversal_attacks_rejected(self):
        """P0-C: Media path traversal attacks must be strictly rejected (400)."""
        from dashboard import sanitize_media_path

        traversal_payloads = [
            "../../../etc/passwd",
            "/etc/shadow",
            "../media/../../secret.txt",
            "/var/log/syslog",
            "media/../../../Windows/System32",
            "proof.jpg/../../evil.sh",
        ]

        for payload in traversal_payloads:
            with self.assertRaises(HTTPException, msg=f"Payload '{payload}' should have been rejected") as ctx:
                sanitize_media_path(payload)
            self.assertEqual(ctx.exception.status_code, 400)

    def test_media_path_valid_resolution(self):
        """P0-C: Valid relative media paths inside media directory resolve cleanly."""
        from dashboard import sanitize_media_path

        res = sanitize_media_path("proof_1.jpg")
        self.assertIsNotNone(res)
        self.assertTrue(res.endswith("proof_1.jpg"))

        # Multiple comma-separated valid images
        res_multi = sanitize_media_path("proof_1.jpg, proof_2.jpg, proof_3.jpg")
        self.assertIsNotNone(res_multi)
        self.assertIn("proof_1.jpg", res_multi)
        self.assertIn("proof_2.jpg", res_multi)
        self.assertIn("proof_3.jpg", res_multi)


if __name__ == '__main__':
    unittest.main()
