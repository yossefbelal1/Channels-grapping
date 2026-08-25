"""
app/validator/contact_extractor.py — Contact & Support Info Extractor
"""

import re

EMAIL_REGEX = re.compile(
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
)

PHONE_REGEX = re.compile(
    r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}'
)

SUPPORT_KEYWORDS = [
    "تواصل", "للتواصل", "للاشتراك", "للحجز", "للدعم", "خدمة العملاء", "الادارة", "الإدارة",
    "المدير", "المشرف", "للاستفسار", "للانضمام", "بوت التواصل", "حساب التواصل", "التواصل معي",
    "contact", "support", "admin", "owner", "vip", "manager", "inquiries"
]


def extract_contacts(text: str, description: str, channel_username: str) -> dict:
    """
    Extracts contact info (website, email, whatsapp, contact_username) from message text & bio description.
    """
    contacts = {
        'website': None,
        'email': None,
        'whatsapp': None,
        'contact_username': None
    }

    combined = f"{text or ''} {description or ''}"
    if not combined.strip():
        return contacts

    # 1. Website
    web_match = re.search(
        r'https?://(?:www\.)?(?!(?:t\.me|telegram\.(?:me|dog|org|space)))([a-zA-Z0-9-]+\.[a-zA-Z]{2,6})[^\s]*',
        combined,
        re.IGNORECASE
    )
    if web_match:
        contacts['website'] = web_match.group(0).rstrip('.,;)!}"\'')

    # 2. Email
    email_match = EMAIL_REGEX.search(combined)
    if email_match:
        contacts['email'] = email_match.group(0).lower()

    # 3. WhatsApp
    wa_match = re.search(r'(?:wa\.me|api\.whatsapp\.com/send\?phone=)(\+?\d+)', combined, re.IGNORECASE)
    if wa_match:
        contacts['whatsapp'] = wa_match.group(1)
    else:
        # Fallback phone search near whatsapp keywords
        if "واتس" in combined or "whatsapp" in combined.lower():
            phone_match = PHONE_REGEX.search(combined)
            if phone_match and len(re.sub(r'\D', '', phone_match.group(0))) >= 8:
                contacts['whatsapp'] = phone_match.group(0).strip()

    # 4. Support / Admin Username (@username)
    channel_clean = (channel_username or '').strip().lstrip('@').lower()
    mentions = re.findall(r'@([a-zA-Z0-9_]{5,32})', combined)

    junk_usernames = {
        'joinchat', 'share', 'addstickers', 'addlist', 'gmail', 'hotmail', 'yahoo', 'outlook',
        'icloud', 'mail', 'yandex', 'protonmail', 'proton', 'telegram', 'spambot', 'sticker',
        'gif', 'bot', 'username', 'ads', 'advertise', 'channel', 'group', 'chat', 'support',
        'help', 'admin', 'contact', 'info', 'service', 'feedback', 'terms', 'privacy'
    }

    # Find first mention that is not the channel's own username and not a junk keyword
    for mention in mentions:
        m_lower = mention.lower()
        if m_lower != channel_clean and m_lower not in junk_usernames:
            if not (m_lower.endswith('bot') or m_lower.endswith('_bot')):
                contacts['contact_username'] = mention
                break

    return contacts
