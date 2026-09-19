"""
tests/test_dashboard_session_auth.py — Direct unit tests for Session Cookie & HttpOnly Auth on Dashboard
"""

import os
import asyncio
import unittest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException, Response, Request


class TestDashboardSessionAuth(unittest.TestCase):

    def setUp(self):
        from dashboard import _get_session_token, dashboard_login, dashboard_logout, dashboard_auth_status, LoginRequest
        self._get_session_token = _get_session_token
        self.dashboard_login = dashboard_login
        self.dashboard_logout = dashboard_logout
        self.dashboard_auth_status = dashboard_auth_status
        self.LoginRequest = LoginRequest

    def test_session_token_generation_deterministic(self):
        token1 = self._get_session_token("secret_123")
        token2 = self._get_session_token("secret_123")
        token_diff = self._get_session_token("secret_456")
        self.assertEqual(token1, token2)
        self.assertNotEqual(token1, token_diff)

    def test_login_success_sets_httponly_cookie(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "DASHBOARD_API_KEY": "test_pass_123"}):
            resp = Response()
            res = asyncio.run(self.dashboard_login(self.LoginRequest(api_key="test_pass_123"), resp))
            self.assertTrue(res["success"])
            # Verify set-cookie header
            set_cookie = resp.headers.get("set-cookie", "")
            self.assertIn("dashboard_session=", set_cookie)
            self.assertIn("HttpOnly", set_cookie)
            self.assertIn("samesite=lax", set_cookie.lower())
            expected_token = self._get_session_token("test_pass_123")
            self.assertIn(expected_token, set_cookie)

    def test_login_failure_with_wrong_key(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "DASHBOARD_API_KEY": "test_pass_123"}):
            resp = Response()
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(self.dashboard_login(self.LoginRequest(api_key="wrong_key"), resp))
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertNotIn("dashboard_session=", resp.headers.get("set-cookie", ""))

    def test_logout_clears_cookie(self):
        resp = Response()
        res = asyncio.run(self.dashboard_logout(resp))
        self.assertTrue(res["success"])
        set_cookie = resp.headers.get("set-cookie", "")
        self.assertIn("dashboard_session=", set_cookie)
        # Deleted cookie sets max-age=0
        self.assertIn("max-age=0", set_cookie.lower())

    def test_verify_auth_with_session_cookie(self):
        from dashboard import verify_dashboard_auth
        req = MagicMock()
        req.headers = {}
        expected_token = self._get_session_token("my_master_key")
        req.cookies = {"dashboard_session": expected_token}

        with patch.dict(os.environ, {"ENVIRONMENT": "production", "DASHBOARD_API_KEY": "my_master_key"}):
            # Valid session cookie authorizes request
            self.assertTrue(verify_dashboard_auth(request=req, header_key=None))

            # Invalid / forged session cookie rejects request
            req.cookies = {"dashboard_session": "forged_token_abc"}
            with self.assertRaises(HTTPException) as ctx:
                verify_dashboard_auth(request=req, header_key=None)
            self.assertEqual(ctx.exception.status_code, 401)

    def test_auth_status_endpoint(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "DASHBOARD_API_KEY": "key_789"}):
            # Unauthenticated request
            req = MagicMock()
            req.cookies = {}
            status_unauthed = asyncio.run(self.dashboard_auth_status(req))
            self.assertFalse(status_unauthed["authenticated"])
            self.assertTrue(status_unauthed["required"])

            # Authenticated request with valid cookie
            valid_token = self._get_session_token("key_789")
            req.cookies = {"dashboard_session": valid_token}
            status_authed = asyncio.run(self.dashboard_auth_status(req))
            self.assertTrue(status_authed["authenticated"])

    def test_serve_dashboard_renders_login_in_production_when_unauthenticated(self):
        from dashboard import serve_dashboard
        req = MagicMock()
        req.cookies = {}
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "DASHBOARD_API_KEY": "key_789"}):
            resp = serve_dashboard(req)
            self.assertEqual(resp.status_code, 200)
            self.assertIn("Secure Sign In", resp.body.decode("utf-8"))
            self.assertIn("Master API Key", resp.body.decode("utf-8"))

    def test_serve_dashboard_renders_app_when_authenticated(self):
        from dashboard import serve_dashboard
        req = MagicMock()
        valid_token = self._get_session_token("key_789")
        req.cookies = {"dashboard_session": valid_token}
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "DASHBOARD_API_KEY": "key_789"}):
            resp = serve_dashboard(req)
            self.assertEqual(resp.status_code, 200)
            self.assertIn("LeadHunter CRM", resp.body.decode("utf-8"))
            self.assertIn("Arabic Forex Discovery Portal", resp.body.decode("utf-8"))

