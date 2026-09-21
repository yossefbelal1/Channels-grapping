import unittest
from unittest.mock import MagicMock, patch

from dashboard import get_discovered_24h, approve_discovered_leads


class TestDiscovered24hAPI(unittest.TestCase):
    @patch("dashboard.get_redis_client")
    @patch("dashboard.get_db_cursor")
    def test_get_discovered_24h_success(self, mock_get_cursor, mock_redis):
        """Test get_discovered_24h returns correct structure, KPI summary, and health."""
        mock_cur = MagicMock()
        mock_get_cursor.return_value.__enter__.return_value = mock_cur

        # 1. Summary row & total count query
        mock_cur.fetchone.side_effect = [
            {
                "total_discovered": 150,
                "qualified_count": 90,
                "rejected_count": 60,
                "with_contact_count": 15,
                "with_whatsapp_count": 2,
                "groups_count": 5,
                "channels_count": 145,
                "avg_score": 35.5,
                "avg_forex_score": 42.0
            },
            {"total_matched": 150}
        ]

        # 2. Hourly throughput, tier rows, top sources, channels
        mock_cur.fetchall.side_effect = [
            [{"hour_label": "02:00", "hour_slot": "2026-09-21 02:00", "total_count": 25, "qualified_count": 15, "rejected_count": 10}],
            [{"tier": "Tier_B", "count": 50}, {"tier": "Tier_C", "count": 40}],
            [{"source": "forward_origin", "method": "forwards", "count": 80}],
            [
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "channel_username": "forex_signals_vip",
                    "member_count": 1500,
                    "description": "Daily Forex signals",
                    "language": "Arabic",
                    "arabic_ratio": 95,
                    "contact_username": "forex_admin",
                    "whatsapp": None,
                    "website": None,
                    "lead_score": 75,
                    "tier": "Tier_B",
                    "status": "new",
                    "discovered_at": "2026-09-21T01:30:00",
                    "last_activity": None,
                    "forex_score": 85,
                    "gold_score": 90,
                    "signal_score": 80,
                    "outreach_priority": "P1",
                    "outreach_priority_score": 85,
                    "outreach_priority_reason": "Active Forex signals channel with contact",
                    "commercial_fit_score": 70,
                    "discovery_source": "forward_origin",
                    "discovery_method": "forwards",
                    "is_group": False,
                    "campaign_status": "pending_review",
                    "campaign_log_id": "22222222-2222-2222-2222-222222222222"
                }
            ]
        ]

        # Redis mock
        r = MagicMock()
        r.get.side_effect = lambda k: "1" if k == "outreach:emergency_stop" else None
        r.llen.return_value = 5
        mock_redis.return_value = r

        res = get_discovered_24h(status=None, tier=None, search=None, limit=100, offset=0)
        self.assertTrue(res["success"])
        self.assertIn("summary", res)
        self.assertEqual(res["summary"]["total_discovered"], 150)
        self.assertEqual(res["summary"]["qualified_count"], 90)
        self.assertEqual(res["summary"]["rejected_count"], 60)
        self.assertEqual(res["summary"]["qualification_rate"], 60.0)
        self.assertEqual(res["summary"]["contact_extraction_rate"], 16.7)
        self.assertIn("system_health", res)
        self.assertTrue(res["system_health"]["kill_switch_active"])
        self.assertEqual(len(res["channels"]), 1)
        self.assertEqual(res["channels"][0]["channel_username"], "forex_signals_vip")

    @patch("dashboard.CampaignRepository.get_active_campaign")
    @patch("dashboard.get_db_cursor")
    def test_approve_discovered_leads_success(self, mock_get_cursor, mock_active_camp):
        """Test approve_discovered_leads approves leads and links to active campaign."""
        mock_active_camp.return_value = {"id": "active-campaign-uuid"}
        mock_cur = MagicMock()
        mock_cur.rowcount = 2
        mock_get_cursor.return_value.__enter__.return_value = mock_cur

        payload = {"lead_ids": ["lead-1", "lead-2"]}
        res = approve_discovered_leads(payload=payload)
        self.assertTrue(res["success"])
        self.assertEqual(res["approved_count"], 4)
        self.assertEqual(res["campaign_id"], "active-campaign-uuid")

    def test_approve_discovered_leads_empty_ids(self):
        """Test approving with empty IDs returns error."""
        res = approve_discovered_leads(payload={"lead_ids": []})
        self.assertFalse(res["success"])
        self.assertIn("No lead_ids provided", res["error"])

    @patch("app.learning.rejection_learner.RejectionLearner.process_rejection")
    @patch("dashboard.get_redis_client")
    @patch("dashboard.get_db_cursor")
    def test_reject_discovered_lead_success(self, mock_get_cursor, mock_redis, mock_process):
        """Test reject_discovered_lead endpoint calls RejectionLearner."""
        from dashboard import reject_discovered_lead
        mock_process.return_value = {
            "success": True,
            "lead_id": "test-lead-uuid",
            "learned_negative_tokens": ["spam", "betting"]
        }
        res = reject_discovered_lead(payload={"lead_id": "test-lead-uuid", "reason": "Non-forex spam"})
        self.assertTrue(res["success"])
        self.assertEqual(res["lead_id"], "test-lead-uuid")
        self.assertIn("spam", res["learned_negative_tokens"])

    def test_reject_discovered_lead_missing_id(self):
        """Test rejecting without lead_id returns error."""
        from dashboard import reject_discovered_lead
        res = reject_discovered_lead(payload={})
        self.assertFalse(res["success"])
        self.assertIn("No lead_id provided", res["error"])

    def test_serve_discovered_24h_page(self):
        """Test serve_discovered_24h_page renders HTML with 24h discovery components."""
        from dashboard import serve_discovered_24h_page
        from starlette.requests import Request

        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {}

        with patch.dict("os.environ", {"ENVIRONMENT": "development", "DASHBOARD_API_KEY": ""}):
            response = serve_discovered_24h_page(mock_request)
            self.assertEqual(response.status_code, 200)
            html = response.body.decode("utf-8")
            self.assertIn('tab-discovered-24h', html)
            self.assertIn('Hourly Discovery Velocity', html)
            self.assertIn('disc24-total', html)
            self.assertIn('batchApproveDiscovered', html)
            self.assertIn('rejectDiscoveredLead', html)
            self.assertIn("switchTab('discovered-24h');", html)


if __name__ == "__main__":
    unittest.main()


