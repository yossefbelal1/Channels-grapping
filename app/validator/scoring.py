"""
app/validator/scoring.py — Arabic NLP & Business Intent Lead Scoring Engine
"""

import re

# Arabic Unicode range regex
ARABIC_CHAR_REGEX = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]')

# High-value Forex/Crypto commercial intent keywords
COMMERCIAL_KEYWORDS = {
    "vip": ["vip", "الخاصة", "الخاص", "اشتراك", "مدفوع", "توصيات vip", "قناة vip", "بريميوم"],
    "account_management": ["إدارة حسابات", "ادارة حسابات", "إدارة المحافظ", "ادارة محافظ", "نسبة أرباح", "حساب ممول"],
    "copy_trading": ["نسخ", "نسخ صفقات", "copy trading", "ربط الحساب", "تداول آلي"],
    "signals": ["توصيات", "تحليل", "صفقة", "صفقات", "هدف", "وقف خسارة", "xauusd", "ذهب", "بيتكوين", "btc", "فوركس"],
    "prop_firms": ["تحدي", "شركة تمويل", "ftmo", "funded", "حساب ممول", "تحديات"]
}


def calculate_arabic_ratio(text: str) -> float:
    """Calculates ratio of Arabic characters relative to total alphabetic characters."""
    if not text:
        return 0.0

    letters = re.findall(r'[a-zA-Z\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]', text)
    if not letters:
        return 0.0

    arabic_chars = [ch for ch in letters if ARABIC_CHAR_REGEX.match(ch)]
    return round(len(arabic_chars) / len(letters), 3)


def calculate_lead_score(
    member_count: int,
    arabic_ratio: float,
    has_contact: bool,
    commercial_flags: dict,
    has_recent_activity: bool = True
) -> tuple:
    """
    Calculates composite lead score (0-100) and lead tier ('Tier 1', 'Tier 2', 'Tier 3', 'Unqualified').
    """
    score = 0

    # 1. Arabic content ratio (0-25 pts)
    if arabic_ratio >= 0.60:
        score += 25
    elif arabic_ratio >= 0.30:
        score += 15
    elif arabic_ratio >= 0.10:
        score += 5

    # 2. Member size (0-25 pts)
    if member_count >= 10000:
        score += 25
    elif member_count >= 3000:
        score += 20
    elif member_count >= 1000:
        score += 15
    elif member_count >= 300:
        score += 10
    elif member_count >= 50:
        score += 5

    # 3. Direct contact resolved (0-20 pts)
    if has_contact:
        score += 20

    # 4. Commercial Offerings (0-20 pts)
    if commercial_flags.get("has_vip"):
        score += 8
    if commercial_flags.get("has_account_management"):
        score += 6
    if commercial_flags.get("has_copy_trading"):
        score += 4
    if commercial_flags.get("has_signals"):
        score += 2

    # 5. Active recent posts (0-10 pts)
    if has_recent_activity:
        score += 10

    # Determine Tier
    if score >= 75:
        tier = "Tier 1"
    elif score >= 50:
        tier = "Tier 2"
    elif score >= 30:
        tier = "Tier 3"
    else:
        tier = "Unqualified"

    return min(100, score), tier
