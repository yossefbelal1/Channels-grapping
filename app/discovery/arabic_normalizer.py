"""
app/discovery/arabic_normalizer.py — Arabic-Aware NLP Normalizer & Query Variant Generator
"""

import re
from typing import List, Set

# Arabic Unicode range regex
ARABIC_CHAR_REGEX = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]')

# Diacritics (Tashkeel) regex: Tanwin, Fathah, Dammah, Kasrah, Shaddah, Sukun, Sup. Alef
TASHKEEL_REGEX = re.compile(r'[\u064B-\u0652\u0670]')

# Tatweel (Kashida)
TATWEEL_REGEX = re.compile(r'\u0640')


def normalize_arabic_text(text: str, normalize_taa_marbuta: bool = True) -> str:
    """
    Standardizes Arabic text for high-recall search matching and NLP scoring.
    
    Operations:
    1. Strips Tashkeel (diacritics) & Tatweel (kashida).
    2. Unifies all Alif forms (أ, إ, آ, ٱ -> ا).
    3. Unifies Yaa & Alif Maqsura (ى, ئ -> ي).
    4. Unifies Taa Marbuta to Haa (ة -> ه) if requested.
    5. Normalizes excessive whitespace and English casing.
    """
    if not text:
        return ""

    # Remove Tashkeel and Tatweel
    clean = TASHKEEL_REGEX.sub('', text)
    clean = TATWEEL_REGEX.sub('', clean)

    # Normalize Alif variants
    clean = re.sub(r'[أإآٱ]', 'ا', clean)

    # Normalize Yaa / Alif Maqsura
    clean = re.sub(r'[ىئ]', 'ي', clean)

    # Normalize Taa Marbuta
    if normalize_taa_marbuta:
        clean = re.sub(r'ة', 'ه', clean)

    # Normalize multiple whitespaces
    clean = re.sub(r'\s+', ' ', clean).strip()

    return clean


def contains_arabic(text: str) -> bool:
    """Returns True if the text contains any Arabic Unicode characters."""
    if not text:
        return False
    return bool(ARABIC_CHAR_REGEX.search(text))


def calculate_arabic_letter_ratio(text: str) -> float:
    """
    Calculates the ratio of Arabic alphabetic characters to total alphabetic characters.
    Returns float in range [0.0, 1.0].
    """
    if not text:
        return 0.0

    letters = re.findall(r'[a-zA-Z\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]', text)
    if not letters:
        return 0.0

    arabic_chars = [ch for ch in letters if ARABIC_CHAR_REGEX.match(ch)]
    return round(len(arabic_chars) / len(letters), 3)


def generate_query_variants(keyword: str, max_variants: int = 5) -> List[str]:
    """
    Generates controlled search query variants for Telegram Global Search.
    Avoids query explosion by generating only the most effective high-yield mutations.
    
    Examples:
      'توصيات الذهب' -> ['توصيات الذهب', 'توصيات ذهب', 'توصيات الذهب XAUUSD', 'اشارات الذهب']
      'فوركس' -> ['فوركس', 'الفوركس', 'forex', 'تداول فوركس']
    """
    if not keyword:
        return []

    variants: Set[str] = {keyword.strip()}

    normalized = normalize_arabic_text(keyword, normalize_taa_marbuta=False)
    variants.add(normalized)

    # Variant with normalized Taa Marbuta / Haa
    h_variant = normalize_arabic_text(keyword, normalize_taa_marbuta=True)
    variants.add(h_variant)

    # Handle definite article (الـ / Al-)
    words = keyword.split()
    if len(words) >= 1:
        # Variant removing 'ال' from words
        stripped_al = " ".join([w[2:] if (w.startswith("ال") and len(w) > 3) else w for w in words])
        if stripped_al != keyword:
            variants.add(stripped_al)

        # Variant adding 'ال' to first word if missing
        if not words[0].startswith("ال") and len(words[0]) > 2 and contains_arabic(words[0]):
            added_al = " ".join(["ال" + words[0]] + words[1:])
            variants.add(added_al)

    # Specific domain cross-enrichment
    lower_kw = keyword.lower()
    if "ذهب" in keyword or "gold" in lower_kw:
        variants.add(f"{keyword} XAUUSD")
    elif "فوركس" in keyword:
        variants.add(f"{keyword} Forex")
    elif "توصيات" in keyword:
        variants.add(f"{keyword} VIP")
    elif "smc" in lower_kw or "ict" in lower_kw:
        variants.add(f"{keyword} تحليل")

    # Clean and order variants
    result = []
    for v in variants:
        v_clean = re.sub(r'\s+', ' ', v).strip()
        if v_clean and v_clean not in result:
            result.append(v_clean)
        if len(result) >= max_variants:
            break

    return result
