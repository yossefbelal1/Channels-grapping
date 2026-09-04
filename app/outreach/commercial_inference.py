"""
app/outreach/commercial_inference.py — Commercial Fit & Service Need Inference Engine

Analyzes channel content, bio, posting velocity, and operational footprint to infer:
1. Business Model Strength (VIP, Copy trading, Broker affiliate, Prop firm, Academy, Subscriptions)
2. Commercial Activity (Promotions, discounts, landing pages, payment methods, CTAs)
3. Operational Complexity (Posting volume, multi-content mixing, structured trade setups, multi-channel links)
4. Likely Service Fit (Channel Management, Advertising Management, Growth, Verification, etc.)
"""

import re
import logging
from typing import Dict, Any, List, Optional, Tuple, Set
from datetime import datetime, timezone, timedelta

from app.outreach.constants import ServiceNeedType

logger = logging.getLogger(__name__)


class CommercialInferenceEngine:
    """
    Infers commercial maturity, monetization intent, and service needs of a channel
    without relying on explicit "wanted" requests.
    """

    # ── Business Model Keywords ────────────────────────────────────────────────
    BM_VIP = [
        "vip", "قناة vip", "قناة خاصة", "القناة الخاصة", "جروب vip", "اشتراك vip",
        "اشتراك شهري", "اشتراك سنوي", "باقة شهرية", "باقات", "رسوم اشتراك", "مدفوع",
        "قناة مدفوعة", "vip signals", "premium", "membership", "عضوية خاصة"
    ]

    BM_COPY_TRADING = [
        "نسخ صفقات", "نسخ الصفقات", "copy trading", "copy trade", "إدارة حسابات",
        "ادارة حسابات", "ادارة محافظ", "إدارة محافظ", "portfolio management",
        "ربط حسابات", "تداول آلي", "بوت نسخ"
    ]

    BM_BROKER_AFFILIATE = [
        "رابط تسجيل", "رابط الوكالة", "وكيل معتمد", "وسيط معتمد", "افتح حسابك برعايتنا",
        "كاش باك", "بونص إيداع", "كود وكالة", "تحت وكالتنا", "سجل تحت وكالتنا",
        "exness", "xm", "ic markets", "fxtm", "avatrade", "tickmill", "windsor",
        "ib", "introducing broker"
    ]

    BM_PROP_FIRM = [
        "حساب ممول", "حسابات ممولة", "شركات التمويل", "تحدي التمويل", "prop firm",
        "funded account", "ftmo", "fundednext", "the funded trader", "mff",
        "اجتياز التحدي", "تقييم التداول", "تداول برأس مال الشركة"
    ]

    BM_ACADEMY = [
        "أكاديمية", "اكاديمية", "كورس مدفوع", "دورة مدفوعة", "تدريب خاص",
        "mentorship", "academy", "course", "دورة احترافية", "ورشة عمل مدفوعة"
    ]

    # ── Commercial Activity Keywords ──────────────────────────────────────────
    COMM_PROMOTIONS = [
        "عرض خاص", "خصم", "خصم خاص", "لفترة محدودة", "العرض ساري", "سارع بالاشتراك",
        "انضموا قبل الحذف", "انضموا قبل اكتمال العدد", "تخفيض", "discount", "special offer",
        "باقي أماكن محدودة", "عرض اليوم", "فرصة ذهبية", "سعر رمزي"
    ]

    COMM_PAYMENT_METHODS = [
        "usdt", "binance", "binance pay", "بينانس", "بينانس باي", "crypto",
        "visa", "mastercard", "perfect money", "skrill", "neteller", "فودافون كاش",
        "stc pay", "trc20", "erc20"
    ]

    COMM_CTAS = [
        "للاشتراك تواصل", "للانضمام تواصل", "للاشتراك راسل", "للحجز تواصل",
        "لفتح حساب تواصل", "سجل معنا عبر", "تواصل مع خدمة العملاء", "تواصل مع الدعم",
        "للاستفسار عن الباقات", "ارسل رسالة للاشتراك", "كلمني خاص للاشتراك",
        "انضم للـ vip", "انضم للقناة الخاصة", "تواصل مع الإدارة", "تواصل مع الادارة",
        "لربط حسابك", "لإدارة حسابك", "للتواصل"
    ]

    # ── Operational Complexity Indicators ─────────────────────────────────────
    TRADE_SETUP_PATTERNS = [
        r'\b(buy|sell|شراء|بيع)\s*(limit|stop|now|ماركت|الآن)?\b',
        r'\b(sl|stop\s*loss|وقف\s*الخسارة|ستوب)\s*[:=\-]?\s*\d+',
        r'\b(tp|tp1|tp2|take\s*profit|هدف|الهدف\s*الأول)\s*[:=\-]?\s*\d+',
        r'\b(xauusd|gold|ذهب|eurusd|gbpusd|us30|nasdaq|nas100)\b'
    ]

    ANALYSIS_PATTERNS = [
        r'تحليل\s*(فني|أسبوعي|يومي|الذهب|العملات)',
        r'مستويات\s*(الدعم|المقاومة|السيولة)',
        r'(order\s*block|fvg|liquidity|smc|ict|فجوة\s*سعرية)',
        r'(شارت|رسم\s*بياني|مناطق\s*العرض\s*والطلب)'
    ]

    @classmethod
    def analyze_channel_commercial_fit(
        cls,
        title: str = "",
        description: str = "",
        recent_messages: Optional[List[Any]] = None,
        contacts_dict: Optional[Dict[str, Any]] = None,
        posts_24h: int = 0,
        posts_7d: int = 0,
        member_count: int = 0
    ) -> Dict[str, Any]:
        """
        Infers commercial fit, business model strength, operational complexity,
        and likely service needs from channel content and operational telemetry.
        """
        recent_messages = recent_messages or []
        contacts_dict = contacts_dict or {}
        now = datetime.now(timezone.utc)

        # Normalize texts
        bio_text = f"{title} {description}".lower()
        
        # Collect post texts, IDs, and dates
        message_records = []
        for msg in recent_messages:
            if isinstance(msg, dict):
                text = msg.get("text") or msg.get("message") or ""
                msg_id = msg.get("id")
                date = msg.get("date")
            else:
                text = getattr(msg, "text", "") or getattr(msg, "message", "") or ""
                msg_id = getattr(msg, "id", None)
                date = getattr(msg, "date", None)
            
            if date and isinstance(date, datetime) and date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            
            message_records.append({
                "text": text,
                "lower": text.lower(),
                "id": msg_id,
                "date": date
            })

        all_posts_text = " ".join(m["lower"] for m in message_records)
        combined_corpus = f"{bio_text} {all_posts_text}"

        # ── 1. Infer Business Models (0 to 20 points) ───────────────────────────
        detected_models = []
        bm_score = 0

        has_vip = any(kw in combined_corpus for kw in cls.BM_VIP)
        if has_vip:
            detected_models.append("vip_subscription")
            bm_score += 12

        has_copy = any(kw in combined_corpus for kw in cls.BM_COPY_TRADING)
        if has_copy:
            detected_models.append("copy_trading_portfolio")
            bm_score += 10

        has_broker = any(kw in combined_corpus for kw in cls.BM_BROKER_AFFILIATE)
        if has_broker:
            detected_models.append("broker_affiliate_ib")
            bm_score += 10

        has_prop = any(kw in combined_corpus for kw in cls.BM_PROP_FIRM)
        if has_prop:
            detected_models.append("prop_firm_challenges")
            bm_score += 8

        has_academy = any(kw in combined_corpus for kw in cls.BM_ACADEMY)
        if has_academy:
            detected_models.append("academy_courses")
            bm_score += 8

        bm_score = min(20, bm_score)

        # ── 2. Infer Commercial Activity & Promotions (0 to 35 points) ─────────
        promo_post_count = 0
        cta_post_count = 0
        payment_methods_found = set()
        evidence_snippets = []
        freshest_commercial_date: Optional[datetime] = None

        for rec in message_records:
            t = rec["lower"]
            is_promo = any(kw in t for kw in cls.COMM_PROMOTIONS)
            is_cta = any(kw in t for kw in cls.COMM_CTAS)
            found_payments = [pm for pm in cls.COMM_PAYMENT_METHODS if pm in t]
            
            all_bm_kws = cls.BM_VIP + cls.BM_COPY_TRADING + cls.BM_BROKER_AFFILIATE + cls.BM_PROP_FIRM + cls.BM_ACADEMY
            has_bm_in_msg = any(kw in t for kw in all_bm_kws)
            
            if is_promo or is_cta or found_payments or has_bm_in_msg:
                if is_promo or has_bm_in_msg:
                    promo_post_count += 1
                if is_cta:
                    cta_post_count += 1
                for pm in found_payments:
                    payment_methods_found.add(pm)

                if rec["date"] and (not freshest_commercial_date or rec["date"] > freshest_commercial_date):
                    freshest_commercial_date = rec["date"]

                if len(evidence_snippets) < 3 and rec["text"].strip():
                    evidence_snippets.append({
                        "message_id": rec["id"],
                        "date": rec["date"].isoformat() if rec["date"] else None,
                        "snippet": rec["text"].strip()[:160]
                    })

        # Score Commercial Fit (0-35)
        comm_fit_score = 0
        if promo_post_count >= 3 or (len(detected_models) >= 1 and promo_post_count >= 1):
            comm_fit_score += 15
        elif promo_post_count >= 1:
            comm_fit_score += 10

        has_bio_cta = ("للتواصل" in bio_text or "تواصل" in bio_text) and len(detected_models) >= 1
        if cta_post_count >= 2 or has_bio_cta:
            comm_fit_score += 10
        elif cta_post_count >= 1:
            comm_fit_score += 6

        if payment_methods_found:
            comm_fit_score += 8  # Concrete monetization method (USDT / Binance Pay)

        # Has private invite link / VIP link
        if "t.me/+" in combined_corpus or "t.me/joinchat/" in combined_corpus:
            comm_fit_score += 4

        comm_fit_score = min(35, comm_fit_score)

        # ── 3. Infer Operational Complexity (0 to 15 points) ───────────────────
        op_complexity_score = 0

        # Frequency / Posting volume (signals active business)
        if posts_24h >= 6 or posts_7d >= 30:
            op_complexity_score += 5
        elif posts_24h >= 2 or posts_7d >= 10:
            op_complexity_score += 3
        elif len(message_records) >= 15:
            op_complexity_score += 2

        # Structured trade setups (SL/TP)
        has_structured_signals = False
        structured_count = 0
        for rec in message_records:
            has_entry = bool(re.search(cls.TRADE_SETUP_PATTERNS[0], rec["lower"]))
            has_sl = bool(re.search(cls.TRADE_SETUP_PATTERNS[1], rec["lower"]))
            has_tp = bool(re.search(cls.TRADE_SETUP_PATTERNS[2], rec["lower"]))
            if has_entry and (has_sl or has_tp):
                structured_count += 1
        if structured_count >= 3:
            has_structured_signals = True
            op_complexity_score += 4
        elif structured_count >= 1:
            has_structured_signals = True
            op_complexity_score += 2

        # Multi-content mixing (signals + technical analysis/charts + promos)
        has_analysis = any(bool(re.search(pat, all_posts_text)) for pat in cls.ANALYSIS_PATTERNS)
        if has_structured_signals and has_analysis:
            op_complexity_score += 3
        elif has_analysis:
            op_complexity_score += 2

        # Ecosystem / Multiple channels (links to results or discussion)
        ecosystem_links = re.findall(r't\.me/([a-zA-Z0-9_]{5,32})', combined_corpus)
        unique_links = set(l.lower() for l in ecosystem_links)
        if len(unique_links) >= 2:
            op_complexity_score += 3

        op_complexity_score = min(15, op_complexity_score)

        # ── 4. Service Fit Prediction (Likely Needs) ───────────────────────────
        likely_services = []

        # Channel Management: high posting load + structured setups + active commercial operations
        if op_complexity_score >= 6 or (posts_24h >= 4 and promo_post_count >= 1) or (len(detected_models) >= 1 and posts_7d >= 15):
            likely_services.append(ServiceNeedType.CHANNEL_MANAGEMENT)

        # Advertising Management: active monetization, promotions, affiliate
        if comm_fit_score >= 18 or "vip_subscription" in detected_models:
            likely_services.append(ServiceNeedType.ADVERTISING_MANAGEMENT)

        # Growth Marketing: commercial channel looking for audience conversion
        if len(detected_models) >= 1 and (comm_fit_score >= 12 or promo_post_count >= 2):
            likely_services.append(ServiceNeedType.GROWTH_MARKETING)

        # Verification: high brand or multi-model commercial channel
        if len(detected_models) >= 2 and comm_fit_score >= 20:
            likely_services.append(ServiceNeedType.VERIFICATION)

        # Account Management: copy trading or portfolio management presence
        if "copy_trading_portfolio" in detected_models:
            likely_services.append(ServiceNeedType.ACCOUNT_MANAGEMENT)

        # Partnerships: broker affiliate or prop firm presence
        if "broker_affiliate_ib" in detected_models or "prop_firm_challenges" in detected_models:
            likely_services.append(ServiceNeedType.PARTNERSHIPS)

        # Content / Media: technical analysis + heavy posting
        if has_analysis and posts_7d >= 15:
            likely_services.append(ServiceNeedType.CONTENT_MEDIA)

        if not likely_services:
            likely_services.append(ServiceNeedType.NONE)

        # ── 5. Freshness Calculation (0 to 5 points) ───────────────────────────
        freshness_score = 0
        freshness_days = 999.0
        if freshest_commercial_date:
            freshness_days = max(0.0, (now - freshest_commercial_date).total_seconds() / 86400.0)
            if freshness_days <= 3.0:
                freshness_score = 5
            elif freshness_days <= 7.0:
                freshness_score = 4
            elif freshness_days <= 14.0:
                freshness_score = 3
            elif freshness_days <= 30.0:
                freshness_score = 2
            elif freshness_days <= 60.0:
                freshness_score = 1
        elif len(detected_models) >= 1 or any(kw in bio_text for kw in cls.BM_VIP + cls.COMM_PROMOTIONS + cls.COMM_CTAS):
            # Bio has active commercial business model (live state)
            freshness_days = 0.0
            freshness_score = 5

        # ── 6. Confidence Computation ──────────────────────────────────────────
        signals_count = len(detected_models) + (1 if promo_post_count > 0 else 0) + (1 if payment_methods_found else 0) + (1 if has_structured_signals else 0)
        confidence = min(0.98, max(0.40, 0.45 + (signals_count * 0.12)))

        return {
            "commercial_fit_score": comm_fit_score,
            "business_model_score": bm_score,
            "operational_complexity_score": op_complexity_score,
            "freshness_score": freshness_score,
            "freshness_days": round(freshness_days, 1) if freshness_days != 999.0 else None,
            "detected_models": detected_models,
            "promo_post_count": promo_post_count,
            "payment_methods": sorted(list(payment_methods_found)),
            "has_structured_signals": has_structured_signals,
            "likely_services": likely_services,
            "confidence": round(confidence, 2),
            "evidence_snippets": evidence_snippets,
            "freshest_commercial_date": freshest_commercial_date.isoformat() if freshest_commercial_date else None
        }
