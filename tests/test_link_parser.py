"""
tests/test_link_parser.py — Unit Tests for Link Parsing & Normalization
"""

import unittest
from app.validator.link_parser import parse_telegram_link, normalize_telegram_link


class TestLinkParser(unittest.TestCase):

    def test_parse_public_username(self):
        link_type, identifier = parse_telegram_link("https://t.me/forex_signals_vip")
        self.assertEqual(link_type, "public")
        self.assertEqual(identifier, "forex_signals_vip")

    def test_parse_public_with_at(self):
        link_type, identifier = parse_telegram_link("https://t.me/arabic_crypto_hub")
        self.assertEqual(link_type, "public")
        self.assertEqual(identifier, "arabic_crypto_hub")

    def test_parse_private_invite_plus(self):
        link_type, identifier = parse_telegram_link("https://t.me/+AbCdEfGhIjKlMnOp")
        self.assertEqual(link_type, "private")
        self.assertEqual(identifier, "AbCdEfGhIjKlMnOp")

    def test_parse_private_joinchat(self):
        link_type, identifier = parse_telegram_link("https://t.me/joinchat/AAAAAFM_q12345")
        self.assertEqual(link_type, "private")
        self.assertEqual(identifier, "AAAAAFM_q12345")

    def test_filter_bots(self):
        link_type, identifier = parse_telegram_link("https://t.me/CryptoAlert_bot")
        self.assertIsNone(link_type)
        self.assertIsNone(identifier)

    def test_filter_junk_usernames(self):
        link_type, identifier = parse_telegram_link("https://t.me/contact")
        self.assertIsNone(link_type)
        self.assertIsNone(identifier)

        link_type, identifier = parse_telegram_link("https://t.me/support")
        self.assertIsNone(link_type)
        self.assertIsNone(identifier)

    def test_normalize_link_variants(self):
        self.assertEqual(normalize_telegram_link("t.me/my_channel"), "https://t.me/my_channel")
        self.assertEqual(normalize_telegram_link("telegram.me/my_channel"), "https://t.me/my_channel")
        self.assertEqual(normalize_telegram_link("http://t.me/my_channel"), "https://t.me/my_channel")
        self.assertEqual(normalize_telegram_link("https://t.me/my_channel"), "https://t.me/my_channel")


if __name__ == '__main__':
    unittest.main()
