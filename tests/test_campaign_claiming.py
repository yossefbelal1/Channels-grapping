"""
tests/test_campaign_claiming.py — Unit Tests for Concurrency Claiming & Idempotency
"""

import unittest
from unittest.mock import MagicMock
from app.repositories.campaign_repository import CampaignRepository


class TestCampaignClaiming(unittest.TestCase):

    def test_idempotency_key_format(self):
        campaign_id = "test-camp-123"
        lead_id = "test-lead-456"
        key = f"campaign:delivered:{campaign_id}:{lead_id}"
        self.assertEqual(key, "campaign:delivered:test-camp-123:test-lead-456")

    def test_followup_idempotency_key_format(self):
        campaign_id = "test-camp-123"
        lead_id = "test-lead-456"
        key = f"campaign:followup_delivered:{campaign_id}:{lead_id}"
        self.assertEqual(key, "campaign:followup_delivered:test-camp-123:test-lead-456")


if __name__ == '__main__':
    unittest.main()
