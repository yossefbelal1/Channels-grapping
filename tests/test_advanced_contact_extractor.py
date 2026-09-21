"""
tests/test_advanced_contact_extractor.py — Comprehensive Unit Tests for Smart Contact Extraction
"""

import pytest
from app.validator.contact_extractor import extract_contacts


def test_user_exact_example_emoji_support():
    desc = "قناة الذئب الأسود للتداول والتوصيات 🐺\n📲 الدعم: @BlackWolf_Support\nانضم لأقوى فريق"
    contacts = extract_contacts(text="", description=desc, channel_username="BlackWolf_Signals")
    
    assert contacts["admin_username"] == "BlackWolf_Support"
    assert contacts["contact_username"] == "BlackWolf_Support"


def test_tme_link_extraction():
    desc = "للاشتراك في باقة الـ VIP وتأكيد الحجز تواصل معي عبر الرابط:\nhttps://t.me/Forex_VIP_Boss"
    contacts = extract_contacts(text="", description=desc, channel_username="DailyForexSignals")
    
    assert contacts["contact_username"] == "Forex_VIP_Boss"


def test_telegram_me_and_short_handle():
    text = "للتواصل مع المدير العام: telegram.me/vip1"
    contacts = extract_contacts(text=text, description="", channel_username="ArabCryptoHub")
    
    assert contacts["contact_username"] == "vip1"


def test_tg_resolve_protocol():
    text = "📩 للاستفسار والحجز: tg://resolve?domain=GoldBooking"
    contacts = extract_contacts(text=text, description="", channel_username="GoldClub")
    
    assert contacts["contact_username"] == "GoldBooking"


def test_owner_vs_admin_separation():
    desc = """
    قناة التوصيات الذهبية
    👑 حسابي الوحيد والرسمي: @ForexCEO
    💬 للإدارة والدعم الفني: @SupportDesk_FX
    """
    contacts = extract_contacts(text="", description=desc, channel_username="GoldSignals")
    
    assert contacts["owner_username"] == "ForexCEO"
    assert contacts["admin_username"] == "SupportDesk_FX"
    # Owner should be the primary contact_username for outbound DM
    assert contacts["contact_username"] == "ForexCEO"


def test_bot_isolation_prefers_human():
    desc = """
    أهلاً بكم في قناة الفوركس
    🤖 بوت الرد الآلي: @ForexHelper_bot
    👤 المدير التنفيذي: @TamerTrader
    """
    contacts = extract_contacts(text="", description=desc, channel_username="ForexChannel")
    
    assert contacts["bot_username"] == "ForexHelper_bot"
    assert contacts["admin_username"] == "TamerTrader"
    assert contacts["contact_username"] == "TamerTrader"


def test_whatsapp_and_phone_extraction():
    desc = """
    للتواصل المباشر مع خدمة العملاء
    واتساب: https://wa.me/971501234567
    """
    contacts = extract_contacts(text="", description=desc, channel_username="DubaiTrading")
    
    assert contacts["whatsapp"] == "971501234567"


def test_ignore_self_username():
    desc = "قناة @DubaiGold الرسمية للتحليلات اليومية"
    contacts = extract_contacts(text="", description=desc, channel_username="DubaiGold")
    
    assert contacts["contact_username"] is None
    assert contacts["owner_username"] is None
    assert contacts["admin_username"] is None


def test_ignore_youtube_and_email_handles():
    desc = "تابعنا على يوتيوب: https://youtube.com/@hendawi2026 أو راسلنا على admin@forexsite.com\nللتواصل تيليجرام: @abu_shaqran"
    contacts = extract_contacts(text="", description=desc, channel_username="abo_shaqran")
    
    assert contacts["contact_username"] == "abu_shaqran"
    assert "hendawi2026" not in [c["value"] for c in contacts["structured_contacts"] if c["type"] in ("owner", "admin", "contact")]


def test_pinned_message_contact_priority():
    pinned = "عرض خاص للأعضاء: تواصل مع الدعم للاشتراك @VIP_Support_Now"
    desc = "قناة التوصيات العامة\nللمتابعة العامة: @General_Info"
    contacts = extract_contacts(text="", description=desc, channel_username="SignalsRoom", pinned_text=pinned)
    
    assert contacts["contact_username"] == "VIP_Support_Now"
    assert contacts["source"] in ("pinned_admin", "pinned_contact")

