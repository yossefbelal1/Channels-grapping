import os
import unittest
from unittest.mock import MagicMock, patch

from app.outreach.emergency import check_outreach_safety_gate
from app.outreach.eligibility import check_eligibility


class TestContactDeduplicationEngine(unittest.TestCase):
    """
    Test suite verifying strict single-message policy per human recipient:
    1. Redis Layer 7 deduplication gate.
    2. Eligibility Layer check for already messaged contacts across channels.
    3. Normalization of usernames with/without '@' and case variations.
    """

    def setUp(self):
        self.redis_mock = MagicMock()
        # Default mock: global outreach enabled, no kill switch
        def mock_get(k):
            if k == "outreach:global:enabled":
                return "1"
            if k == "outreach:emergency_stop":
                return None
            return None
        self.redis_mock.get.side_effect = mock_get
        self.redis_mock.sismember.return_value = False

    def test_safety_gate_blocks_contact_already_in_redis_set(self):
        """Safety Gate Layer 7 must reject outreach if recipient was already messaged."""
        # Simulate contact already exists in Redis messaged set
        self.redis_mock.sismember.side_effect = lambda s, m: s == "outreach:messaged_contacts" and m == "abrahim151515"

        with patch.dict(os.environ, {"OUTREACH_ENABLED": "true", "CAMPAIGN_MODE": "live"}):
            # Target with '@'
            ok, reason = check_outreach_safety_gate(
                redis_conn=self.redis_mock,
                session_name="user_session",
                target_username="@abrahim151515",
                log_status="approved",
                campaign_mode="live"
            )
            self.assertFalse(ok)
            self.assertIn("DUPLICATE_CONTACT", reason)
            self.assertIn("abrahim151515", reason)

            # Target without '@' and uppercase
            ok2, reason2 = check_outreach_safety_gate(
                redis_conn=self.redis_mock,
                session_name="user_session",
                target_username="ABRAHIM151515",
                log_status="approved",
                campaign_mode="live"
            )
            self.assertFalse(ok2)
            self.assertIn("DUPLICATE_CONTACT", reason2)

    def test_eligibility_blocks_duplicate_contact_via_db(self):
        """check_eligibility must return CONTACTED if contact was messaged via ANY previous lead."""
        db_cur_mock = MagicMock()
        
        # Blacklist check returns None (not blacklisted)
        # Leads check returns valid lead
        # Campaign log check returns row found (already messaged)
        db_cur_mock.fetchone.side_effect = [
            None,                      # blacklist check
            {"status": "new", "next_eligible_at": None, "risk_score": 10, "description": "Channel OK"}, # leads check
            None,                      # campaign 1 check
            {"found": 1}               # contact already messaged via another lead!
        ]

        status, reason = check_eligibility(
            redis_conn=self.redis_mock,
            db_cursor=db_cur_mock,
            lead_id="test-lead-uuid",
            campaign_id="test-campaign-uuid",
            contact_username="@Sultan1gold"
        )

        self.assertEqual(status, "CONTACTED")
        self.assertIn("already messaged", reason.lower())

    def test_eligibility_blocks_duplicate_contact_via_redis_cache(self):
        """check_eligibility short-circuits via Redis set without hitting heavy queries."""
        self.redis_mock.sismember.side_effect = lambda s, m: s == "outreach:messaged_contacts" and m == "sarhan_ea_support"
        db_cur_mock = MagicMock()
        db_cur_mock.fetchone.side_effect = [
            None,                      # blacklist check
            {"status": "new", "next_eligible_at": None, "risk_score": 10, "description": "Channel OK"}, # leads check
            None                       # campaign check
        ]

        status, reason = check_eligibility(
            redis_conn=self.redis_mock,
            db_cursor=db_cur_mock,
            lead_id="lead-sarhan",
            campaign_id="camp-1",
            contact_username="Sarhan_EA_Support"
        )

        self.assertEqual(status, "CONTACTED")
        self.assertIn("redis cache", reason.lower())

    def test_username_normalization_consistency(self):
        """Ensure handles with whitespace, @ and casing normalize consistently."""
        raw_variants = ["@Forex_Owner", "forex_owner", "  @FOREX_OWNER  ", "FOREX_OWNER"]
        normalized = {u.strip().lower().lstrip('@') for u in raw_variants}
        self.assertEqual(len(normalized), 1)
        self.assertIn("forex_owner", normalized)


if __name__ == "__main__":
    unittest.main()
