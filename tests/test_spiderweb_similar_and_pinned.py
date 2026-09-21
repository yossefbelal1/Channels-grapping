import unittest
from unittest.mock import MagicMock, patch, AsyncMock

from app.validator.contact_extractor import extract_contacts
from app.discovery.similar_channels_crawler import SimilarChannelsCrawler


class TestSpiderwebSimilarAndPinned(unittest.TestCase):
    def test_pinned_message_contact_extraction_almaalforex(self):
        """Test pinned message contact extraction specifically matches @G0ld_c for AlmaalFOREX."""
        pinned_text = """🔥 تفاصيل القناة الخاصة | خبراء تداول الذهب

💎 الاشتراك الشهري: $100

🎁 مجاناً تحت الوكالة
عند فتح حساب تداول عن طريق الوكالة وتحقيق شروط الإيداع المطلوبة، تحصل على عضوية القناة الخاصة مجاناً.

📌 مميزات القناة الخاصة:

• 📊 توصيات تداول الذهب بشكل يومي
• 🎯 نقاط دخول وأهداف ووقف خسارة
• 🛡️ إدارة وتأمين للصفقات
• 📈 تحليلات السوق وحركة الذهب
• ⚡ تنبيهات سريعة أثناء حركة السوق
• 💬 متابعة ودعم للمشتركين

للاشتراك أو معرفة شروط الوكالة، راسل الإدارة 📩
@G0ld_c"""

        res = extract_contacts(
            text="بعض التوصيات اليومية وتحليلات الذهب",
            description="أكاديمية الخبراء | خبراء تداول الذهب",
            channel_username="AlmaalFOREX",
            pinned_text=pinned_text
        )

        self.assertEqual(res["contact_username"], "G0ld_c")
        self.assertEqual(res["admin_username"], "G0ld_c")
        self.assertEqual(res["source"], "pinned_admin")
        self.assertIn("G0ld_c", [sc["value"] for sc in res["structured_contacts"]])

    def test_pinned_message_priority_over_body_text(self):
        """Test contacts in pinned message take precedence over mentions in regular posts."""
        pinned_text = "للاشتراك في باقات VIP تواصل مع المدير: @RealManager"
        body_text = "شكرا لـ @RandomMember على الملاحظة"

        res = extract_contacts(
            text=body_text,
            description="قناة تداول عملات",
            channel_username="TestChannel",
            pinned_text=pinned_text
        )

        self.assertEqual(res["contact_username"], "RealManager")
        self.assertEqual(res["source"], "pinned_admin")

    @patch("app.discovery.similar_channels_crawler.get_redis_client")
    @patch("app.discovery.similar_channels_crawler.get_db_connection")
    def test_crawler_session_rotation(self, mock_db, mock_redis):
        """Test crawler rotates across research pool and never uses user_session."""
        crawler = SimilarChannelsCrawler(sessions=["acc_1", "acc_2", "acc_3"])
        
        s1 = crawler._get_next_session()
        s2 = crawler._get_next_session()
        s3 = crawler._get_next_session()
        s4 = crawler._get_next_session()

        self.assertEqual(s1, "acc_1")
        self.assertEqual(s2, "acc_2")
        self.assertEqual(s3, "acc_3")
        self.assertEqual(s4, "acc_1")
        self.assertNotIn("user_session", crawler.sessions)


if __name__ == "__main__":
    unittest.main()
