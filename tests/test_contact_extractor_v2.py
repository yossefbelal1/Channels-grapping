"""
Unit tests for Structured Contact Extractor
"""

import pytest
from app.validator.contact_extractor import extract_contacts


def test_extract_contacts_owner_and_admin():
    bio = """
    قناة التوصيات الذهبية الرسمية
    مؤسس القناة: @Ahmed_Forex_Owner
    للإدارة والدعم الفني: @Support_Admin_FX
    للتواصل واتساب: https://wa.me/201207500631
    موقعنا الرسمي: https://goldtrading-arabic.com
    رابط الباقات: https://linktr.ee/arabicforex
    """

    contacts = extract_contacts(text="", description=bio, channel_username="gold_channel")

    assert contacts["owner_username"] == "Ahmed_Forex_Owner"
    assert contacts["admin_username"] == "Support_Admin_FX"
    assert contacts["whatsapp"] == "201207500631"
    assert "goldtrading-arabic.com" in (contacts["website"] or "")
    
    types = [sc["type"] for sc in contacts["structured_contacts"]]
    assert "owner" in types
    assert "admin" in types
    assert "whatsapp" in types
    assert "linktree" in types
    assert "website" in types
