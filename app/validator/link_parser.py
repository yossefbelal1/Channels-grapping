"""
app/validator/link_parser.py — Telegram Link & Username Parsing Utilities
"""

import re

TELEGRAM_LINK_REGEX = re.compile(
    r'(?:https?://)?(?:t\.me|telegram\.me)/(?:joinchat/)?\+?[a-zA-Z0-9_.-]+',
    re.IGNORECASE
)

USERNAME_REGEX = re.compile(r'@([a-zA-Z0-9_]{5,32})')

JUNK_USERNAMES = {
    'joinchat', 'share', 'addstickers', 'addlist', 'gmail', 'hotmail', 'yahoo', 'outlook',
    'icloud', 'mail', 'yandex', 'protonmail', 'proton', 'telegram', 'spambot', 'sticker',
    'gif', 'bot', 'username', 'ads', 'advertise', 'channel', 'group', 'chat', 'support',
    'help', 'admin', 'contact', 'info', 'service', 'feedback', 'terms', 'privacy'
}


def parse_telegram_link(link: str) -> tuple:
    """
    Parses a Telegram link and returns (link_type, identifier).
    link_type: 'public' or 'private'
    """
    if not link:
        return None, None
    link = link.strip()

    if '(?:t.me|telegram.me)/+' in link or '/+' in link:
        parts = link.split('/+')
        if len(parts) > 1:
            return 'private', parts[1].split('/')[0]

    private_joinchat = re.search(r'(?:t\.me|telegram\.me)/joinchat/([a-zA-Z0-9_-]+)', link, re.IGNORECASE)
    if private_joinchat:
        return 'private', private_joinchat.group(1)

    public_match = re.search(r'(?:t\.me|telegram\.me)/([a-zA-Z0-9_]{5,32})', link, re.IGNORECASE)
    if public_match:
        username = public_match.group(1)
        username_lower = username.lower()
        if username_lower not in JUNK_USERNAMES:
            if not (username_lower.endswith('bot') or username_lower.endswith('_bot')):
                return 'public', username

    return None, None


def normalize_telegram_link(link: str) -> str:
    """Normalizes Telegram link to https://t.me/username standard format."""
    clean = link.strip()
    if clean.lower().startswith("https://"):
        clean = clean[8:]
    elif clean.lower().startswith("http://"):
        clean = clean[7:]

    if clean.lower().startswith("telegram.me/"):
        clean = "t.me/" + clean[12:]

    if not clean.lower().startswith("t.me/"):
        return f"https://t.me/{clean}"
    return f"https://{clean}"
