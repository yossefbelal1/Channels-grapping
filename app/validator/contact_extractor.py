"""
app/validator/contact_extractor.py — Advanced Multi-Surface Contact & Owner Extractor

Extracts structured contact info (owner username, admin username, contact username,
bot username, WhatsApp numbers, website, Linktree, social links) with full support for:
- Telegram handles (@username) from 3 to 32 characters
- t.me/ and telegram.me/ direct links
- tg://resolve?domain= links
- Emoji and decorative bullet prefixes (📲 💬 📞 👤 📩 👉 👇 👑 🎯 ✨ etc.)
- Rich Arabic & English intent triggers (الدعم, تواصل معي, للاشتراك, حسابي الوحيد, الادارة, etc.)
- Strict separation of human contacts vs bot contacts
"""

import re
from typing import Dict, Any, List, Optional, Set

EMAIL_REGEX = re.compile(
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
)

PHONE_REGEX = re.compile(
    r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}'
)

# Common Telegram decorative & communication emojis
EMOJI_PATTERN = r'[\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff\ufe0f]'

# Junk usernames to exclude
JUNK_USERNAMES: Set[str] = {
    'joinchat', 'share', 'addstickers', 'addlist', 'gmail', 'hotmail', 'yahoo', 'outlook',
    'icloud', 'mail', 'yandex', 'protonmail', 'proton', 'telegram', 'spambot', 'sticker',
    'gif', 'bot', 'username', 'ads', 'advertise', 'channel', 'group', 'chat', 'support',
    'help', 'admin', 'contact', 'info', 'service', 'feedback', 'terms', 'privacy',
    'proxy', 'socks', 'setlanguage', 'everyone', 'vip', 'premium', 'signals', 'signal',
    'forex', 'crypto', 'gold', 'trade', 'trading', 'club', 'team', 'c', 's', 'm', 'i'
}

# 1. Owner triggers (high confidence of being channel creator/owner)
OWNER_TRIGGERS = [
    r'مؤسس\s*(?:القناة|القناه)?',
    r'مؤسس',
    r'صاحب\s*(?:القناة|القناه|العمل)?',
    r'مالك\s*(?:القناة|القناه)?',
    r'المالك',
    r'المؤسس',
    r'حسابي\s*(?:الوحيد|الشخصي|الرسمي|الخاص)?',
    r'مدير\s*(?:القناة|القناه)',
    r'👑',
    r'owner',
    r'founder',
    r'creator',
    r'ceo',
    r'channel\s*owner',
    r'creator\s*account',
    r'my\s*(?:personal\s*)?account',
]

# 2. Admin & Support triggers (support team, official desk, managers, ads)
ADMIN_TRIGGERS = [
    r'(?:لل|ل)?(?:ال)?دعم\s*(?:الفني)?',
    r'دعم\s*(?:القناة|القناه|الاعضاء|المشتركين)?',
    r'(?:لل|ل)?خدم[ةه]\s*(?:العملاء|المشتركين)',
    r'(?:لل|ل)?(?:ال)?[إا]دار[ةه]\s*(?:العامة|الرسمية)?',
    r'معرف\s*(?:الادارة|الإدارة|الدعم)',
    r'راسل\s*(?:الادارة|الإدارة|الدعم|المدير|المشرف)',
    r'تراسل\s*(?:الادارة|الإدارة|الدعم|المدير|المشرف)',
    r'مراسلة\s*(?:الادارة|الإدارة|الدعم)',
    r'حساب\s*(?:الادارة|الإدارة|الدعم|الوكالة)',
    r'شروط\s*الوكالة',
    r'تحت\s*الوكالة',
    r'(?:لل|ل)?(?:ال)?مدير\s*(?:العام|التنفيذي|المسؤول|المسئول)?',
    r'(?:لل|ل)?(?:ال)?مشرف\s*(?:العام|المسؤول|المسئول)?',
    r'(?:لل|ل)?(?:ال)?مس[ؤئ]ول\s*(?:العام)?',
    r'مدير\s*(?:الإعلانات|الاعلانات|الاعلان|الإعلان)',
    r'مسؤول\s*(?:الإعلانات|الاعلانات|الاعلان|الإعلان)',
    r'مسئول\s*(?:الإعلانات|الاعلانات|الاعلان|الإعلان)',
    r'للاعلانات',
    r'للإعلانات',
    r'للاعلان',
    r'للإعلان',
    r'تبادل\s*(?:إعلاني|اعلاني)',
    r'لتبادل\s*(?:الإعلانات|الاعلانات)',
    r'للتعاون\s*(?:التجاري|الإعلاني|الاعلاني)?',
    r'تعاون\s*(?:إعلاني|اعلاني|تجاري)',
    r'ادمن',
    r'أدمن',
    r'admin',
    r'administrator',
    r'support',
    r'manager',
    r'helpdesk',
    r'customer\s*service',
    r'official\s*desk',
    r'contact\s*admin',
    r'ads\s*manager',
    r'marketing\s*manager',
]

# 3. Outreach / Subscription / Contact triggers (VIP subscriptions, direct messages)
CONTACT_TRIGGERS = [
    r'تواصل\s*معي',
    r'تواصل\s*معنا',
    r'للتواصل\s*معي',
    r'للتواصل\s*معنا',
    r'للتواصل',
    r'تواصل',
    r'تواصلوا',
    r'تواصل\s*للاعلان',
    r'تواصل\s*للإعلان',
    r'تواصل\s*للاشتراك',
    r'تواصل\s*للتعاون',
    r'للراغبين\s*بالتواصل',
    r'للاستفسار\s*والتواصل',
    r'راسلني',
    r'راسلنا',
    r'للمراسلة',
    r'مراسلة',
    r'كلمني',
    r'ارسل\s*لي',
    r'ارسل\s*لنا',
    r'خاص',
    r'الخاص',
    r'تواصل\s*خاص',
    r'راسلني\s*خاص',
    r'كلمني\s*خاص',
    r'للاشتراك\s*(?:بالـ\s*vip|في\s*الـ\s*vip|بالقناة\s*الخاصة|بالقناه\s*الخاصه|أو\s*معرفة\s*شروط\s*الوكالة|او\s*معرفة\s*شروط\s*الوكالة)?',
    r'القناة\s*الخاص[ةه]',
    r'اشتراك\s*(?:vip)?',
    r'للانضمام',
    r'انضمام',
    r'للحجز\s*(?:والاستفسار)?',
    r'حجز\s*مقعد',
    r'حجز',
    r'للاستفسار',
    r'استفسار',
    r'استفسارات',
    r'contact\s*me',
    r'contact\s*us',
    r'contact',
    r'reach\s*me',
    r'reach\s*us',
    r'reach\s*out',
    r'message\s*me',
    r'send\s*(?:a\s*)?message',
    r'write\s*(?:to\s*)?us',
    r'follow\s*us',
    r'dm',
    r'pm',
    r'inquiries',
    r'inquiry',
    r'subscribe',
    r'subscription',
    r'vip',
    r'📞',
    r'📲',
    r'💬',
    r'📩',
]

# 4. Analyst & Trader triggers (market analysts, mentors, coaches)
ANALYST_TRIGGERS = [
    r'المحلل\s*(?:الفني|المالي)?',
    r'محلل\s*(?:الفني|المالي|القناة|القناه)?',
    r'المهندس',
    r'مهندس',
    r'الكابتن',
    r'كابتن',
    r'الخبير',
    r'خبير\s*(?:التداول|الفوركس|الذهب)?',
    r'trader',
    r'analyst',
    r'mentor',
    r'coach',
    r'فريق\s*العمل',
    r'حساب\s*(?:التواصل|المتابعة|الردود)',
    r'للمزيد\s*والتواصل',
    r'لأي\s*استفسار',
]

# Combined trigger regexes
OWNER_RE = re.compile(r'(?:' + '|'.join(OWNER_TRIGGERS) + r')', re.IGNORECASE)
ADMIN_RE = re.compile(r'(?:' + '|'.join(ADMIN_TRIGGERS) + r')', re.IGNORECASE)
CONTACT_RE = re.compile(r'(?:' + '|'.join(CONTACT_TRIGGERS) + r')', re.IGNORECASE)
ANALYST_RE = re.compile(r'(?:' + '|'.join(ANALYST_TRIGGERS) + r')', re.IGNORECASE)
ALL_CONTACT_TRIGGERS_RE = re.compile(r'(?:' + '|'.join(OWNER_TRIGGERS + ADMIN_TRIGGERS + CONTACT_TRIGGERS + ANALYST_TRIGGERS) + r')', re.IGNORECASE)

# Regex pattern matching any Telegram handle or URL enclosed in a single non-capturing group:
# Uses negative lookbehind (?<![a-zA-Z0-9._/-]) to avoid capturing YouTube/TikTok handles or email addresses
TG_HANDLE_OR_URL_PATTERN = re.compile(
    r'(?:(?:https?://)?(?:t\.me|telegram\.(?:me|dog))/([a-zA-Z0-9_]{3,35})|'
    r'tg://resolve\?domain=([a-zA-Z0-9_]{3,35})|'
    r'(?<![a-zA-Z0-9._/-])@([a-zA-Z0-9_]{3,35}))',
    re.IGNORECASE
)


def _clean_username(raw: Optional[str]) -> Optional[str]:
    """Cleans punctuation, slashes, and leading @ from username candidate."""
    if not raw:
        return None
    cleaned = raw.strip().lstrip('@').lstrip('/').rstrip('.,;:)!?*~`"\'/\\')
    while cleaned.endswith('_') and len(cleaned) > 3:
        cleaned = cleaned[:-1]
    while cleaned.startswith('_') and len(cleaned) > 3:
        cleaned = cleaned[1:]
    cleaned = cleaned.strip()
    if 3 <= len(cleaned) <= 35:
        return cleaned
    return None


def _is_bot(username: str) -> bool:
    """Returns True if username is clearly an automated Telegram bot."""
    if not username:
        return False
    u_lower = username.lower()
    return u_lower.endswith('bot') or u_lower.endswith('_bot')


def _extract_handles_from_line(line: str) -> List[str]:
    """Extracts all Telegram handles or t.me links from a single text line."""
    handles = []
    for match in TG_HANDLE_OR_URL_PATTERN.finditer(line):
        for group_idx in (1, 2, 3):
            val = match.group(group_idx)
            if val:
                cleaned = _clean_username(val)
                if cleaned and cleaned not in handles:
                    handles.append(cleaned)
    return handles


def extract_contacts(
    text: str,
    description: str,
    channel_username: str,
    pinned_text: Optional[str] = None
) -> Dict[str, Any]:
    """
    Extracts structured contact info (owner, admin, general contact, bot, whatsapp,
    website, Linktree, social links) from text, description, and pinned message.
    Pinned message has top priority for admin/subscription contacts.
    """
    contacts: Dict[str, Any] = {
        'website': None,
        'email': None,
        'whatsapp': None,
        'contact_username': None,
        'admin_username': None,
        'owner_username': None,
        'analyst_username': None,
        'contact_name': None,
        'bot_username': None,
        'social_links': [],
        'structured_contacts': [],
        'source': 'unknown'
    }

    desc_clean = description or ''
    text_clean = text or ''
    pinned_clean = pinned_text or ''
    combined = f"{pinned_clean}\n{desc_clean}\n{text_clean}".strip()
    if not combined:
        return contacts

    channel_clean = (channel_username or '').strip().lstrip('@').lower()

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Website & Linktree Extraction
    # ─────────────────────────────────────────────────────────────────────────
    web_matches = re.findall(
        r'https?://(?:www\.)?(?!(?:t\.me|telegram\.(?:me|dog|org|space)|wa\.me|api\.whatsapp\.com|whatsapp\.com))([a-zA-Z0-9-]+\.[a-zA-Z]{2,6}[^\s]*)',
        combined,
        re.IGNORECASE
    )
    for web in web_matches:
        full_url = f"https://{web}".rstrip('.,;)!}"\'')
        url_lower = full_url.lower()
        if "linktr.ee" in url_lower:
            contacts['structured_contacts'].append({"type": "linktree", "value": full_url, "confidence": 95})
        elif any(s in url_lower for s in ["instagram.com", "youtube.com", "twitter.com", "x.com", "tiktok.com", "facebook.com"]):
            if full_url not in contacts['social_links']:
                contacts['social_links'].append(full_url)
                contacts['structured_contacts'].append({"type": "social", "value": full_url, "confidence": 90})
        elif not contacts['website']:
            contacts['website'] = full_url
            contacts['structured_contacts'].append({"type": "website", "value": full_url, "confidence": 90})

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Email Extraction
    # ─────────────────────────────────────────────────────────────────────────
    email_match = EMAIL_REGEX.search(combined)
    if email_match:
        email = email_match.group(0).lower()
        contacts['email'] = email
        contacts['structured_contacts'].append({"type": "email", "value": email, "confidence": 95})

    # ─────────────────────────────────────────────────────────────────────────
    # 3. WhatsApp Extraction (wa.me or international phone regex)
    # ─────────────────────────────────────────────────────────────────────────
    wa_match = re.search(
        r'(?:wa\.me/|api\.whatsapp\.com/send\?phone=|whatsapp:)\+?([0-9]{9,16})',
        combined,
        re.IGNORECASE
    )
    if wa_match:
        phone = wa_match.group(1)
        contacts['whatsapp'] = phone
        contacts['structured_contacts'].append({"type": "whatsapp", "value": phone, "confidence": 100})
    else:
        # Check standard phone numbers near WhatsApp or contact keywords
        phone_match = re.search(
            r'\+?(966|971|965|968|973|962|961|963|967|964|20|90|44|1)[0-9\s-]{7,15}',
            combined
        )
        if phone_match and ("واتس" in combined or "whatsapp" in combined.lower() or "هاتف" in combined or "phone" in combined.lower()):
            clean_phone = re.sub(r'[\s-]', '', phone_match.group(0)).lstrip('+')
            if len(clean_phone) >= 8:
                contacts['whatsapp'] = clean_phone
                contacts['structured_contacts'].append({"type": "whatsapp", "value": clean_phone, "confidence": 85})

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Telegram Handle & Contact Extraction
    # ─────────────────────────────────────────────────────────────────────────
    def is_valid_cand(cand: Optional[str]) -> bool:
        if not cand:
            return False
        c_lower = cand.lower()
        if c_lower == channel_clean:
            return False
        if c_lower in JUNK_USERNAMES:
            return False
        if c_lower.startswith('+'):  # private invite hash
            return False
        return True

    # Scan lines in pinned message first, then description (official bio), then messages text
    all_unattributed_handles: List[str] = []

    sources = []
    if pinned_clean:
        sources.append(('pinned', pinned_clean))
    if desc_clean:
        sources.append(('bio', desc_clean))
    if text_clean:
        sources.append(('text', text_clean))

    for source_type, content in sources:
        if not content:
            continue
        lines = content.split('\n')
        for i, line in enumerate(lines):
            line_str = line.strip()
            if not line_str:
                continue

            handles_in_line = _extract_handles_from_line(line_str)
            if not handles_in_line:
                continue

            # Check previous non-empty line to catch multi-line triggers: e.g. "راسل الإدارة 📩\n@G0ld_c"
            prev_line = ""
            for j in range(i - 1, -1, -1):
                if lines[j].strip():
                    prev_line = lines[j].strip()
                    break

            eval_text = f"{prev_line} {line_str}" if prev_line else line_str

            # Classify line by priority: Owner > Admin > Analyst > Contact
            is_owner_line = bool(OWNER_RE.search(eval_text))
            is_admin_line = bool(ADMIN_RE.search(eval_text))
            is_analyst_line = bool(ANALYST_RE.search(eval_text))
            is_contact_line = bool(CONTACT_RE.search(eval_text))

            for h in handles_in_line:
                if not is_valid_cand(h):
                    continue

                if _is_bot(h):
                    if not contacts['bot_username']:
                        contacts['bot_username'] = h
                    continue

                if is_owner_line and not contacts['owner_username']:
                    contacts['owner_username'] = h
                    contacts['structured_contacts'].append({"type": "owner", "value": h, "confidence": 95})
                    if contacts['source'] == 'unknown':
                        contacts['source'] = f"{source_type}_owner"
                elif is_admin_line and not contacts['admin_username']:
                    contacts['admin_username'] = h
                    contacts['structured_contacts'].append({"type": "admin", "value": h, "confidence": 90})
                    if contacts['source'] == 'unknown':
                        contacts['source'] = f"{source_type}_admin"
                elif is_analyst_line and not contacts.get('analyst_username'):
                    contacts['analyst_username'] = h
                    contacts['structured_contacts'].append({"type": "analyst", "value": h, "confidence": 90})
                    if contacts['source'] == 'unknown':
                        contacts['source'] = f"{source_type}_analyst"
                elif is_contact_line and not contacts['contact_username']:
                    contacts['contact_username'] = h
                    contacts['structured_contacts'].append({"type": "contact", "value": h, "confidence": 85})
                    if contacts['source'] == 'unknown':
                        contacts['source'] = f"{source_type}_contact"
                else:
                    if h not in all_unattributed_handles:
                        all_unattributed_handles.append(h)

    # Fallback to unattributed handles if contact_username is still empty
    if not (contacts['owner_username'] or contacts['admin_username'] or contacts.get('analyst_username') or contacts['contact_username']):
        for h in all_unattributed_handles:
            if is_valid_cand(h) and not _is_bot(h):
                contacts['contact_username'] = h
                contacts['source'] = 'fallback_mention'
                contacts['structured_contacts'].append({"type": "contact", "value": h, "confidence": 70})
                break

    # Consolidate primary contact_username:
    # Priority: owner_username > admin_username > analyst_username > contact_username
    if not contacts['contact_username']:
        if contacts['owner_username']:
            contacts['contact_username'] = contacts['owner_username']
        elif contacts['admin_username']:
            contacts['contact_username'] = contacts['admin_username']
        elif contacts.get('analyst_username'):
            contacts['contact_username'] = contacts['analyst_username']

    return contacts


def is_contact_mention(text: str, mention: str) -> bool:
    """
    Determines if an @mention in a post occurs within a contact, support, admin, or analyst context
    (e.g., 'للتواصل @handle', 'المحلل @handle', 'الدعم @handle', 'حسابي @handle').
    If True, the mention represents a contact person for the channel, NOT an independent channel!
    """
    if not text or not mention:
        return False
        
    m_clean = re.escape(mention.lstrip('@'))
    
    # 1. Search line by line for precise context
    for line in text.split('\n'):
        if re.search(r'@?' + m_clean + r'\b', line, re.IGNORECASE):
            if ALL_CONTACT_TRIGGERS_RE.search(line):
                return True

    # 2. Window-based check: check 80 chars before and 40 chars after the mention
    for m in re.finditer(r'@?' + m_clean + r'\b', text, re.IGNORECASE):
        start = max(0, m.start() - 80)
        end = min(len(text), m.end() + 40)
        window = text[start:end]
        if ALL_CONTACT_TRIGGERS_RE.search(window):
            return True
            
    return False


def extract_contacts_from_messages(
    messages: List[Any],
    description: str,
    channel_username: str,
    pinned_text: Optional[str] = None
) -> Dict[str, Any]:
    """
    Enhanced multi-surface contact extractor operating directly on Telethon Message objects.
    Parses both message text and Telethon message entities:
    - MessageEntityMention: @username handles
    - MessageEntityTextUrl: hidden markdown hyperlinks like [تواصل معنا](https://t.me/admin)
    - MessageEntityUrl: raw t.me/ or telegram.me/ links
    - MessageEntityPhone / MessageEntityEmail
    """
    synthesized_lines: List[str] = []

    for msg in (messages or []):
        if not msg:
            continue

        m_text = getattr(msg, 'message', None) or getattr(msg, 'text', '') or ''
        if m_text:
            synthesized_lines.append(m_text)

        # Inspect Telethon entities if present
        entities = getattr(msg, 'entities', None) or []
        for ent in entities:
            try:
                ent_type = ent.__class__.__name__

                # 1. Hidden hyperlink (e.g. [تواصل معنا](https://t.me/admin_handle))
                if ent_type == 'MessageEntityTextUrl' or hasattr(ent, 'url'):
                    url = getattr(ent, 'url', '') or ''
                    offset = getattr(ent, 'offset', 0)
                    length = getattr(ent, 'length', 0)
                    anchor = m_text[offset:offset+length] if (m_text and length > 0) else ''

                    target_handles = _extract_handles_from_line(url)
                    for h in target_handles:
                        if anchor:
                            synthesized_lines.append(f"{anchor} @{h}")
                        else:
                            synthesized_lines.append(f"تواصل @{h}")

                # 2. Direct mention entity
                elif ent_type == 'MessageEntityMention':
                    offset = getattr(ent, 'offset', 0)
                    length = getattr(ent, 'length', 0)
                    mention_text = m_text[offset:offset+length] if (m_text and length > 0) else ''
                    if mention_text:
                        synthesized_lines.append(mention_text)
            except Exception:
                pass

    aggregated_text = "\n".join(synthesized_lines)
    return extract_contacts(
        text=aggregated_text,
        description=description,
        channel_username=channel_username,
        pinned_text=pinned_text
    )

