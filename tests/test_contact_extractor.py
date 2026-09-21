"""
tests/test_contact_extractor.py — Unit Tests for Contact Info Extraction
"""

import unittest
from app.validator.contact_extractor import extract_contacts


class TestContactExtractor(unittest.TestCase):

    def test_extract_website(self):
        text = "زوروا موقعنا الرسمي https://forextrading-arab.com لمعرفة التفاصيل"
        contacts = extract_contacts(text, "", "my_channel")
        self.assertEqual(contacts['website'], "https://forextrading-arab.com")

    def test_ignore_telegram_website(self):
        text = "تابعونا على https://t.me/another_channel"
        contacts = extract_contacts(text, "", "my_channel")
        self.assertIsNone(contacts['website'])

    def test_extract_email(self):
        desc = "For business inquiries: support@arabicforex.net"
        contacts = extract_contacts("", desc, "my_channel")
        self.assertEqual(contacts['email'], "support@arabicforex.net")

    def test_extract_whatsapp(self):
        text = "للاشتراك في الـ VIP تواصل واتساب: https://wa.me/201234567890"
        contacts = extract_contacts(text, "", "my_channel")
        self.assertEqual(contacts['whatsapp'], "201234567890")

    def test_extract_admin_username(self):
        desc = "قناة التوصيات الرسمية. للتواصل والاشتراك: @Ahmed_Forex_Manager"
        contacts = extract_contacts("", desc, "channel_main")
        self.assertEqual(contacts['contact_username'], "Ahmed_Forex_Manager")

    def test_ignore_channel_self_username(self):
        desc = "قناتنا @channel_main للأخبار والتحليلات"
        contacts = extract_contacts("", desc, "channel_main")
        self.assertIsNone(contacts['contact_username'])

    def test_ignore_bot_mentions(self):
        desc = "بوت الرد التلقائي: @SignalsAlert_bot"
        contacts = extract_contacts("", desc, "channel_main")
        self.assertIsNone(contacts['contact_username'])


    def test_extract_pinned_admin_handle(self):
        pinned = "📩 للاشتراك أو معرفة شروط الوكالة، راسل الإدارة: @G0ld_c"
        contacts = extract_contacts("", "", "almaalforex", pinned_text=pinned)
        self.assertEqual(contacts['contact_username'], "G0ld_c")
        self.assertEqual(contacts['admin_username'], "G0ld_c")

    def test_extract_multiline_support_handle(self):
        desc = "📲 الدعم:\n@BlackWolf_Support"
        contacts = extract_contacts("", desc, "test_channel")
        self.assertEqual(contacts['contact_username'], "BlackWolf_Support")

    def test_extract_analyst_multiline_handle(self):
        pinned = "🔥 خسران وعايز تعوّض؟\n📩 تواصل :\n@KSA_Trader11"
        contacts = extract_contacts("", "", "ABOSALEM2003", pinned_text=pinned)
        self.assertEqual(contacts['contact_username'], "KSA_Trader11")


if __name__ == '__main__':
    unittest.main()
