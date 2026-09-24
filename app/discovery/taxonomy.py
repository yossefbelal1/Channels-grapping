"""
app/discovery/taxonomy.py — Structured Hierarchical Arabic Forex & Commercial Keyword Taxonomy
Contains 100+ precision-tuned keywords spanning Forex, Gold, Crypto, Indices, SMC/ICT,
Commercial Offerings (VIP, Account Management, Copy Trading), and Contact Extraction.
"""

from typing import Dict, List, Set
from app.discovery.arabic_normalizer import normalize_arabic_text

KEYWORD_TAXONOMY: Dict[str, List[str]] = {
    # ── 1. Core Forex & Currency Trading ─────────────────────────────────────
    "FOREX": [
        "فوركس", "الفوركس", "تداول العملات", "سوق العملات", "عملات أجنبية",
        "forex", "forex arabic", "forex signals", "forex trading", "fx",
        "eurusd", "gbpusd", "usdjpy", "audusd", "usdcad", "nzdusd", "usdchf", "gbpjpy", "eurjpy",
        "الرافعة المالية", "اللوت", "السبريد", "البيب", "pips", "لوت ميكرو",
        "تحليل فني", "تحليل أساسي", "شارت", "مستويات الدعم والمقاومة", "برايس اكشن",
        "price action", "ترند صاعد", "ترند هابط", "شموع يابانية", "تداول الفوركس", "سوق الفوركس"
    ],

    # ── 2. Gold & Commodities Trading (High Volume Niche) ─────────────────────
    # NOTE: Never include bare "ذهب" alone to prevent false positives with Arabic past-tense "ذهب" (went) or "مذهب"
    "GOLD_XAUUSD": [
        "الذهب", "تداول الذهب", "توصيات الذهب", "تحليل الذهب", "صفقات الذهب", "اشارات الذهب",
        "شارت الذهب", "سعر الذهب مباشر", "أونصة الذهب", "سبائك الذهب", "معدن الذهب", "عقود الذهب",
        "شراء الذهب", "بيع الذهب", "ذهب فوركس", "xauusd", "xau/usd", "gold", "gold signals",
        "gold trading", "تحليل المعدن الأصفر", "تداول الذهب اليوم", "xagusd", "فضة", "الفضة"
    ],

    # ── 3. Indices & Equity Markets ──────────────────────────────────────────
    "INDICES": [
        "داو جونز", "ناسداك", "us30", "nasdaq", "dow jones", "spx500", "us100",
        "مؤشر داو جونز", "مؤشر ناسداك", "تحليل us30", "توصيات us30", "صفقات ناسداك",
        "مؤشرات أمريكية", "dax", "dax40", "nikkei", "الداوجونز", "الناسداك"
    ],

    # ── 4. Modern Methodology: SMC & ICT ─────────────────────────────────────
    "SMC_ICT": [
        "سمارت موني", "مفهوم المال الذكي", "smart money concept", "smc", "ict",
        "كورس ict", "تحليل smc", "اوردر بلوك", "order block", "ob", "fvg",
        "fair value gap", "فجوة سعرية", "هندسة السيولة", "liquidity", "سحب السيولة",
        "bos", "break of structure", "choch", "change of character", "inducement",
        "منطقة عرض وطلب", "supply and demand", "مناطق الشراء المؤسسي", "صناع السوق"
    ],

    # ── 5. Trading Styles (Scalping, Day Trading, Swing) ───────────────────────
    "TRADING_STYLES": [
        "سكالبينج", "scalping", "صفقات سريعة", "سكالب", "تداول يومي", "day trading",
        "سولينج", "swing trading", "تداول لحظي", "مضاربة سريعة", "مضاربة لحظية",
        "استراتيجية تداول", "مؤشرات فنية", "مؤشر rsi", "مؤشر macd", "البولنجر باند"
    ],

    # ── 6. Signals & Live Trade Setups ─────────────────────────────────────────
    "SIGNALS": [
        "توصيات", "توصيات مجانية", "توصيات vip", "إشارات تداول", "اشارات فوركس",
        "صفقة شراء", "صفقة بيع", "buy limit", "sell limit", "buy stop", "sell stop",
        "هدف أول", "هدف ثاني", "وقف الخسارة", "stop loss", "sl", "tp", "take profit",
        "تحقيق الهدف", "ضرب الهدف", "دخول صفقة", "تأمين الصفقة", "حجز أرباح"
    ],

    # ── 7. Brokers & Trading Platforms ─────────────────────────────────────────
    "BROKERS_PLATFORMS": [
        "وسيط فوركس", "شركة وساطة", "وسيط مرخص", "بروكر", "broker",
        "mt4", "mt5", "metatrader", "ميتاتريدر", "tradingview", "تريدنج فيو",
        "exness", "xm", "ic markets", "fxtm", "avatrade", "tickmill", "windsor",
        "حساب ecn", "حساب إسلامي", "بدون فوائد ربوية", "سواب فري", "swap free"
    ],

    # ── 8. Prop Firms & Funded Accounts (Fast Growing in Arabic Market) ────────
    "PROP_FIRMS": [
        "حساب ممول", "حسابات ممولة", "حسابات مموله", "شركات التمويل", "تحدي التمويل", "prop firm",
        "funded account", "ftmo", "fundednext", "the funded trader", "mff",
        "تحدي شركة تمويل", "اجتياز التحدي", "تقييم التداول", "تداول برأس مال الشركة"
    ],

    # ── 9. Commercial Offerings (Account Management, Copy Trading, VIP Subscriptions)
    "COMMERCIAL_SERVICES": [
        "إدارة حسابات", "ادارة حسابات", "إدارة الحسابات", "ادارة الحسابات", "اداره حسابات",
        "إدارة محافظ", "ادارة محافظ", "إدارة المحافظ", "ادارة المحافظ", "اداره محافظ",
        "إدارة رأس المال", "ادارة راس المال", "ادارة الصفقات", "إدارة الصفقات",
        "نسبة أرباح", "تقاسم أرباح", "عمولة أرباح",
        "نسخ صفقات", "نسخ تداول", "copy trading", "copy trade", "ربط حسابات",
        "تداول آلي", "أنظمة تداول آلية", "انظمة تداول الية", "بوت تداول", "بوتات التداول", "اكسبيرت", "expert advisor",
        "اشتراك شهري", "اشتراك سنوي", "باقات الاشتراك", "باقة vip", "قناة مدفوعة", "vip signals",
        "قناة vip", "قناه vip", "توصيات vip", "قناة خاصة", "قناه خاصه", "توصيات خاصة", "توصيات خاصه",
        "vip مجانا", "vip مجاناً", "اشتراك vip", "حجز مقعد",
        "وكالة", "شروط الوكالة", "تحت وكالتنا", "كود الوكالة", "رابط الوكالة", "فتح حساب برعايتنا",
        "رابط إحالة", "كاش باك فوركس", "ib", "وسيط معرف", "بونص تداول", "بونص إيداع"
    ],

    # ── 10. Direct Contact & Manager Triggers ──────────────────────────────────
    "CONTACT_ADMIN": [
        "للتواصل", "تواصل معي", "تواصل معنا", "راسلنا", "راسلني", "للاستفسار", "للاستفسارات",
        "خدمة العملاء", "الدعم الفني", "معرف التواصل", "حساب التواصل", "معرف المدير",
        "مدير القناة", "ادمن القناة", "أدمن القناة", "المدير العام", "المشرف العام", "مدير الحسابات",
        "مسؤول القناة", "مسئول القناة", "مسؤول الاعلانات", "مدير الاعلانات", "مدير الإعلانات",
        "للاعلانات", "للإعلانات", "تبادل اعلاني", "تبادل إعلاني", "للتعاون الإعلاني", "للتعاون التجاري",
        "للاشتراك في vip", "للاشتراك vip", "للانضمام الى vip", "للاشتراك بالقناة الخاصة",
        "احجز مقعدك", "لطلب الاشتراك", "لتفعيل الاشتراك", "تواصل خاص", "راسلني خاص",
        "admin", "contact", "support", "manager", "owner", "official desk", "inquiries"
    ],

    # ── 11. Crypto & Futures (Arabic Cross-over) ───────────────────────────────
    "CRYPTO_ARABIC": [
        "كريبتو", "تداول الكريبتو", "عملات رقمية", "العملات الرقمية", "بيتكوين",
        "btc", "eth", "sol", "بينانس", "منصة بينانس", "binance", "bybit", "باي بيت",
        "فيوتشر", "futures", "توصيات كريبتو", "usdt", "دفع usdt", "بينانس باي",
        "p2p تداول", "توصيات فيوتشر", "توصيات سبوت", "مضاربة كريبتو", "تحليل البيتكوين",
        "صفقات كريبتو", "إشارات كريبتو", "بينانس فيوتشر", "تداول العملات الرقمية",
        "عملات انفجارية", "بوت كريبتو", "شراء btc", "تحليل الكريبتو"
    ]
}

# Category Scoring Weights (Normalized to sum to 100)
TAXONOMY_WEIGHTS: Dict[str, int] = {
    "FOREX": 25,
    "GOLD_XAUUSD": 20,
    "INDICES": 10,
    "SIGNALS": 15,
    "COMMERCIAL_SERVICES": 15,
    "SMC_ICT": 5,
    "PROP_FIRMS": 4,
    "BROKERS_PLATFORMS": 3,
    "TRADING_STYLES": 2,
    "CRYPTO_ARABIC": 1
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


def get_commercial_keywords() -> List[str]:
    """Returns all commercial service keywords."""
    return KEYWORD_TAXONOMY.get("COMMERCIAL_SERVICES", [])


def get_contact_keywords() -> List[str]:
    """Returns all contact and admin extraction keywords."""
    return KEYWORD_TAXONOMY.get("CONTACT_ADMIN", [])


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
