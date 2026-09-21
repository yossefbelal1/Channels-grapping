"""
tests/test_rejection_learning.py — Unit Tests for Rejection Learning Engine
"""

import unittest
from unittest.mock import MagicMock, patch
from app.learning.rejection_learner import RejectionLearner


class TestRejectionLearner(unittest.TestCase):

    def test_rejection_without_db_returns_error(self):
        res = RejectionLearner.process_rejection(lead_id="fake-id", reason="Spam", db_conn=None)
        self.assertFalse(res["success"])
        self.assertIn("Database connection unavailable", res["error"])

    def test_process_rejection_full_flow(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        # 1. Mock lead row fetch
        mock_cur.fetchone.return_value = {
            "id": "11111111-1111-1111-1111-111111111111",
            "channel_username": "dubai_gambling_slots",
            "description": "كازينو ومراهنات وسلوتس اونلاين ارباح مضاعفة يوميا",
            "metadata": {"title": "كازينو دبي وسلوتس"},
            "lead_score": 50,
            "tier": "Tier_C",
            "status": "new"
        }

        # 2. Mock posts fetch
        mock_cur.fetchall.return_value = [
            {"message_text": "اشترك في كازينو 1xbet وسلوتس مجانية مع كود خصم"},
            {"message_text": "روليت وبوكر ومراهنات رياضية مباشرة"}
        ]

        mock_redis = MagicMock()
        mock_km = MagicMock()

        res = RejectionLearner.process_rejection(
            lead_id="11111111-1111-1111-1111-111111111111",
            reason="Gambling / Non-financial spam",
            db_conn=mock_conn,
            redis_conn=mock_redis,
            knowledge_model=mock_km
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["channel_username"], "dubai_gambling_slots")
        self.assertEqual(res["status"], "rejected")
        self.assertTrue(len(res["learned_negative_tokens"]) > 0)

        # Verify DB commit was called
        mock_conn.commit.assert_called_once()

        # Verify Redis sync was called with negative sets
        mock_redis.sadd.assert_called()

        # Verify KnowledgeModel reloaded
        mock_km.load_from_db.assert_called_once_with(mock_conn)


if __name__ == "__main__":
    unittest.main()
