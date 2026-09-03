"""
app/discovery/taxonomy.py — Structured Hierarchical Arabic Forex Keyword Taxonomy
"""

from typing import Dict, List, Set
from app.discovery.arabic_normalizer import normalize_arabic_text

KEYWORD_TAXONOMY: Dict[str, List[str]] = {
    # ── 1. Core Forex & Currency Trading ─────────────────────────────────────
    "FOREX": [
        "فوركس", "الفوركس", "تداول العملات", "سوق العملات", "عملات أجنبية",
        "forex", "forex arabic", "forex signals", "forex trading", "fx",
        "eurusd", "gbpusd", "usdjpy", "audusd", "usdcad", "nzdusd", "usdchf",
        "الرافعة المالية", "اللوت", "السبريد", "البيب", "pips", "لوت ميكرو",
        "تحليل فني", "تحليل أساسي", "شارت", "مستويات الدعم والمقاومة", "برايس اكشن",
        "price action", "ترند صاعد", "ترند هابط", "شموع يابانية"
    ],

    # ── 2. Gold & Commodities Trading (High Volume Niche) ─────────────────────
    "GOLD_XAUUSD": [
        "ذهب", "الذهب", "توصيات الذهب", "تحليل الذهب", "صفقات الذهب", "اشارات الذهب",
        "xauusd", "xau/usd", "gold", "gold signals", "gold trading", "تحليل المعدن الأصفر",
        "أونصة الذهب", "سعر الذهب مباشر", "تداول الذهب اليوم", "ذهب فوركس", "سبائك ذهب"
    ],

    # ── 3. Modern Methodology: SMC & ICT ─────────────────────────────────────
    "SMC_ICT": [
        "سمارت موني", "مفهوم المال الذكي", "smart money concept", "smc", "ict",
        "كورس ict", "تحليل smc", "اوردر بلوك", "order block", "ob", "fvg",
        "fair value gap", "فجوة سعرية", "هندسة السيولة", "liquidity", "سحب السيولة",
        "bos", "break of structure", "choch", "change of character", "inducement",
        "منطقة عرض وطلب", "supply and demand", "مناطق الشراء المؤسسي", "صناع السوق"
    ],

    # ── 4. Trading Styles (Scalping, Day Trading, Swing) ───────────────────────
    "TRADING_STYLES": [
        "سكالبينج", "scalping", "صفقات سريعة", "سكالب", "تداول يومي", "day trading",
        "سولينج", "swing trading", "تداول لحظي", "مضاربة سريعة", "مضاربة لحظية",
        "استراتيجية تداول", "مؤشرات فنية", "مؤشر rsi", "مؤشر macd", "البولنجر باند"
    ],

    # ── 5. Signals & Live Trade Setups ─────────────────────────────────────────
    "SIGNALS": [
        "توصيات", "توصيات مجانية", "توصيات vip", "إشارات تداول", "اشارات فوركس",
        "صفقة شراء", "صفقة بيع", "buy limit", "sell limit", "buy stop", "sell stop",
        "هدف أول", "هدف ثاني", "وقف الخسارة", "stop loss", "sl", "tp", "take profit",
        "تحقيق الهدف", "ضرب الهدف", "دخول صفقة", "تأمين الصفقة", "حجز أرباح"
    ],

    # ── 6. Brokers & Trading Platforms ─────────────────────────────────────────
    "BROKERS_PLATFORMS": [
        "وسيط فوركس", "شركة وساطة", "وسيط مرخص", "بروكر", "broker",
        "mt4", "mt5", "metatrader", "ميتاتريدر", "tradingview", "تريدنج فيو",
        "exness", "xm", "ic markets", "fxtm", "avatrade", "tickmill", "windsor",
        "حساب ecn", "حساب إسلامي", "بدون فوائد ربوية", "سواب فري", "swap free"
    ],

    # ── 7. Prop Firms & Funded Accounts (Fast Growing in Arabic Market) ────────
    "PROP_FIRMS": [
        "حساب ممول", "حسابات ممولة", "شركات التمويل", "تحدي التمويل", "prop firm",
        "funded account", "ftmo", "fundednext", "the funded trader", "mff",
        "تحدي شركة تمويل", "اجتياز التحدي", "تقييم التداول", "تداول برأس مال الشركة"
    ],

    # ── 8. Commercial Offerings (Account Management, Copy Trading, Subscriptions)
    "COMMERCIAL_SERVICES": [
        "إدارة حسابات", "ادارة محافظ", "ادارة حسابات فوركس", "نسبة أرباح",
        "نسخ صفقات", "copy trading", "ربط حسابات", "تداول آلي", "بوت تداول",
        "اشتراك شهري", "اشتراك سنوي", "قناة مدفوعة", "vip signals", "رابط إحالة",
        "كاش باك فوركس", "ib", "وسيط معرف", "بونص تداول", "بونص إيداع"
    ],

    # ── 9. Crypto & Futures (Arabic Cross-over) ────────────────────────────────
    "CRYPTO_ARABIC": [
        "كريبتو", "تداول الكريبتو", "عملات رقمية", "بيتكوين", "btc", "eth", "sol",
        "بينانس", "منصة بينانس", "binance", "فيوتشر", "futures", "توصيات كريبتو",
        "usdt", "دفع usdt", "بينانس باي", "p2p تداول"
    ]
}

# Category Scoring Weights (Normalized to sum to 100)
TAXONOMY_WEIGHTS: Dict[str, int] = {
    "FOREX": 30,
    "GOLD_XAUUSD": 20,
    "SIGNALS": 15,
    "SMC_ICT": 10,
    "COMMERCIAL_SERVICES": 10,
    "PROP_FIRMS": 5,
    "BROKERS_PLATFORMS": 5,
    "TRADING_STYLES": 3,
    "CRYPTO_ARABIC": 2
}


def get_all_keywords() -> List[str]:
    """Returns a deduplicated master list of all keywords across all taxonomy categories."""
    seen: Set[str] = set()
    result: List[str] = []
    for category, keywords in KEYWORD_TAXONOMY.items():
        for kw in keywords:
            kw_clean = kw.strip()
            if kw_clean and kw_clean.lower() not in seen:
                seen.add(kw_clean.lower())
                result.append(kw_clean)
    return result


def get_category_keywords(category: str) -> List[str]:
    """Returns keywords for a specific category."""
    return KEYWORD_TAXONOMY.get(category, [])


def classify_text_taxonomy(text: str) -> Dict[str, List[str]]:
    """
    Scans a given text (bio, description, or post collection) against the keyword taxonomy.
    Returns a dictionary of category -> list of matched keywords for scoring & evidence tracking.
    """
    if not text:
        return {cat: [] for cat in KEYWORD_TAXONOMY}

    normalized_text = normalize_arabic_text(text.lower())
    matches: Dict[str, List[str]] = {cat: [] for cat in KEYWORD_TAXONOMY}

    for category, keywords in KEYWORD_TAXONOMY.items():
        for kw in keywords:
            kw_norm = normalize_arabic_text(kw.lower())
            if kw_norm in normalized_text:
                matches[category].append(kw)

    return matches
