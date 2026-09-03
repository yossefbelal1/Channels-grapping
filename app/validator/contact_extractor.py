"""
app/validator/contact_extractor.py — Structured Contact & Owner Info Extractor
"""

import re
from typing import Dict, Any, List, Optional

EMAIL_REGEX = re.compile(
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
)

PHONE_REGEX = re.compile(
    r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}'
)

OWNER_KEYWORDS = ["مؤسس", "صاحب القناة", "مالك القناة", "owner", "founder", "creator"]
ADMIN_KEYWORDS = ["الادارة", "الإدارة", "المدير", "المشرف", "admin", "manager", "support", "خدمة العملاء"]
SUPPORT_KEYWORDS = [
    "تواصل", "للتواصل", "للاشتراك", "للحجز", "للدعم", "خدمة العملاء", "الادارة", "الإدارة",
    "المدير", "المشرف", "للاستفسار", "للانضمام", "بوت التواصل", "حساب التواصل", "التواصل معي",
    "contact", "support", "admin", "owner", "vip", "manager", "inquiries"
]

JUNK_USERNAMES = {
    'joinchat', 'share', 'addstickers', 'addlist', 'gmail', 'hotmail', 'yahoo', 'outlook',
    'icloud', 'mail', 'yandex', 'protonmail', 'proton', 'telegram', 'spambot', 'sticker',
    'gif', 'bot', 'username', 'ads', 'advertise', 'channel', 'group', 'chat', 'support',
    'help', 'admin', 'contact', 'info', 'service', 'feedback', 'terms', 'privacy'
}


def extract_contacts(text: str, description: str, channel_username: str) -> Dict[str, Any]:
    """
    Extracts structured contact info (website, email, whatsapp, contact_username,
    admin_username, owner_username, social_links) and returns structured list.
    """
    contacts: Dict[str, Any] = {
        'website': None,
        'email': None,
        'whatsapp': None,
        'contact_username': None,
        'admin_username': None,
        'owner_username': None,
        'social_links': [],
        'structured_contacts': []
    }

    combined = f"{text or ''} {description or ''}"
    if not combined.strip():
        return contacts

    channel_clean = (channel_username or '').strip().lstrip('@').lower()

    # 1. Website & Linktree
    web_matches = re.findall(
        r'https?://(?:www\.)?(?!(?:t\.me|telegram\.(?:me|dog|org|space)|wa\.me|api\.whatsapp\.com|whatsapp\.com))([a-zA-Z0-9-]+\.[a-zA-Z]{2,6}[^\s]*)',
        combined,
        re.IGNORECASE
    )
    for web in web_matches:
        full_url = f"https://{web}".rstrip('.,;)!}"\'')
        if "linktr.ee" in full_url.lower():
            contacts['structured_contacts'].append({"type": "linktree", "value": full_url, "confidence": 95})
        elif any(s in full_url.lower() for s in ["instagram.com", "youtube.com", "twitter.com", "x.com", "tiktok.com"]):
            contacts['social_links'].append(full_url)
            contacts['structured_contacts'].append({"type": "social", "value": full_url, "confidence": 90})
        elif not contacts['website']:
            contacts['website'] = full_url
            contacts['structured_contacts'].append({"type": "website", "value": full_url, "confidence": 90})

    # 2. Email
    email_match = EMAIL_REGEX.search(combined)
    if email_match:
        email = email_match.group(0).lower()
        contacts['email'] = email
        contacts['structured_contacts'].append({"type": "email", "value": email, "confidence": 95})

    # 3. WhatsApp
    wa_match = re.search(r'(?:wa\.me/|api\.whatsapp\.com/send\?phone=)(\+?\d+)', combined, re.IGNORECASE)
    if wa_match:
        phone = wa_match.group(1)
        contacts['whatsapp'] = phone
        contacts['structured_contacts'].append({"type": "whatsapp", "value": phone, "confidence": 100})
    else:
        # Fallback phone search near whatsapp keywords
        if "واتس" in combined or "whatsapp" in combined.lower():
            phone_match = PHONE_REGEX.search(combined)
            if phone_match and len(re.sub(r'\D', '', phone_match.group(0))) >= 8:
                phone = phone_match.group(0).strip()
                contacts['whatsapp'] = phone
                contacts['structured_contacts'].append({"type": "whatsapp", "value": phone, "confidence": 85})

    # 4. Usernames & Roles Extraction (@mentions)
    lines = combined.split("\n")
    for line in lines:
        line_clean = line.strip()
        line_lower = line_clean.lower()
        mentions_in_line = re.findall(r'@([a-zA-Z0-9_]{5,32})', line_clean)

        for mention in mentions_in_line:
            m_lower = mention.lower()
            if m_lower == channel_clean or m_lower in JUNK_USERNAMES or m_lower.endswith("bot") or m_lower.endswith("_bot"):
                continue

            # Check for owner designation
            if any(ow in line_lower for ow in OWNER_KEYWORDS):
                contacts['owner_username'] = mention
                contacts['structured_contacts'].append({"type": "owner", "value": mention, "confidence": 90})
            # Check for admin designation
            elif any(ad in line_lower for ad in ADMIN_KEYWORDS):
                contacts['admin_username'] = mention
                contacts['structured_contacts'].append({"type": "admin", "value": mention, "confidence": 85})
            # General contact
            elif not contacts['contact_username']:
                contacts['contact_username'] = mention
                contacts['structured_contacts'].append({"type": "contact", "value": mention, "confidence": 75})

    # If contact_username is still empty, pick first valid mention
    if not contacts['contact_username']:
        all_mentions = re.findall(r'@([a-zA-Z0-9_]{5,32})', combined)
        for mention in all_mentions:
            m_lower = mention.lower()
            if m_lower != channel_clean and m_lower not in JUNK_USERNAMES and not (m_lower.endswith("bot") or m_lower.endswith("_bot")):
                contacts['contact_username'] = mention
                contacts['structured_contacts'].append({"type": "contact", "value": mention, "confidence": 70})
                break

    return contacts
