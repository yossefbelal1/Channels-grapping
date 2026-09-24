"""
tests/test_contact_extractor_v3.py — Tests for extract_contacts_from_messages & Telethon Entity Extraction
"""

import unittest
from unittest.mock import MagicMock
from app.validator.contact_extractor import extract_contacts_from_messages


class TestContactExtractorV3(unittest.TestCase):

    def test_extract_hidden_markdown_hyperlink_entity(self):
        """
        Verify that [للتواصل اضغط هنا](https://t.me/ForexAdminVIP) is extracted
        even when the message text does NOT contain @ or t.me directly.
        """
        # Message text: "للاشتراك في القناة الخاصة اضغط هنا للتواصل معنا"
        text = "للاشتراك في القناة الخاصة اضغط هنا للتواصل معنا"
        # Entity starts at "اضغط هنا للتواصل معنا"
        mock_entity = MagicMock()
        mock_entity.__class__.__name__ = 'MessageEntityTextUrl'
        mock_entity.url = "https://t.me/ForexAdminVIP"
        mock_entity.offset = 26
        mock_entity.length = 20

        mock_msg = MagicMock()
        mock_msg.message = text
        mock_msg.text = text
        mock_msg.entities = [mock_entity]

        contacts = extract_contacts_from_messages(
            messages=[mock_msg],
            description="",
            channel_username="SomeChannel"
        )

        self.assertEqual(contacts["contact_username"], "ForexAdminVIP")
        self.assertIn("ForexAdminVIP", [c["value"] for c in contacts["structured_contacts"]])

    def test_extract_entity_mention(self):
        """Verify Telethon MessageEntityMention is parsed correctly."""
        text = "للتواصل مع الإدارة: @SupportDeskAdmin"
        mock_entity = MagicMock()
        mock_entity.__class__.__name__ = 'MessageEntityMention'
        mock_entity.offset = 20
        mock_entity.length = 17

        mock_msg = MagicMock()
        mock_msg.message = text
        mock_msg.text = text
        mock_msg.entities = [mock_entity]

        contacts = extract_contacts_from_messages(
            messages=[mock_msg],
            description="",
            channel_username="GoldChannel"
        )

        self.assertEqual(contacts["admin_username"], "SupportDeskAdmin")
        self.assertEqual(contacts["contact_username"], "SupportDeskAdmin")

    def test_expanded_arabic_keywords(self):
        """Verify newly expanded triggers like 'راسلنا' and 'للاعلانات' work."""
        mock_msg1 = MagicMock()
        mock_msg1.message = "راسلنا للاعلانات والتبادل الإعلاني: @AdsManagerForex"
        mock_msg1.text = mock_msg1.message
        mock_msg1.entities = []

        contacts = extract_contacts_from_messages(
            messages=[mock_msg1],
            description="",
            channel_username="ArabicForexSignals"
        )

        self.assertEqual(contacts["admin_username"], "AdsManagerForex")
        self.assertEqual(contacts["contact_username"], "AdsManagerForex")


if __name__ == "__main__":
    unittest.main()
