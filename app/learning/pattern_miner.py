"""
app/learning/pattern_miner.py — Contrastive Pattern & Feature Mining Engine

Extracts generalized trading terminology, n-grams, symbols, syntax patterns,
and service phrases from positive (Gold) and negative corpora.
Applies contrastive log-odds scoring and anti-overfitting filtering.
"""

import re
import math
import logging
from typing import Dict, Any, List, Set, Tuple, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

# Personal & brand identifiers that must never be memorized or promoted as trading signals
BLOCKED_IDENTIFIER_TOKENS = {
    "tamer", "tamerads", "tamerads1", "admin", "owner", "contact",
    "developer", "whatsapp", "telegram", "channel", "group", "link",
    "http", "https", "joinchat", "bot"
}

ARABIC_STOPWORDS = {
    "في", "من", "على", "إلى", "عن", "مع", "هذا", "هذه", "تم", "كان", "كانت",
    "ان", "أن", "إن", "هو", "هي", "التي", "الذي", "الذين", "كل", "ما", "لا",
    "لم", "لن", "او", "أو", "ثم", "قد", "لو", "حتى", "اذا", "إذا", "بين",
    "ذلك", "تلك", "هناك", "نحن", "هم", "انت", "أنت", "انتم", "فقط", "كما",
    "بعد", "قبل", "عند", "خلال", "حيث", "اي", "أي", "جدا", "جداً", "غير",
    "يا", "نحو", "لدى", "منذ", "دون", "نفس", "بعض", "ولا", "بها", "له", "لها",
    "لنا", "لهم", "به", "بهم", "فإن", "وان", "وهو", "وهي", "وهذا", "وهذه"
}

ENGLISH_STOPWORDS = {
    "the", "and", "or", "in", "on", "at", "to", "for", "is", "are", "of",
    "with", "by", "from", "it", "this", "that", "these", "those", "we", "you",
    "our", "your", "my", "me", "us", "they", "them", "their", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "can", "could", "should", "not", "no", "yes", "but", "if", "as", "all",
    "any", "so", "than", "too", "very", "just", "now", "here", "there"
}

# Common currency/crypto ticker and asset symbols
SYMBOL_REGEX = re.compile(
    r"\b([A-Z]{3,6}(?:/[A-Z]{3,6}|USDT|USD|BUSD|BTC|ETH)?)\b",
    re.IGNORECASE
)

# Structural trading post patterns
SYNTAX_PATTERNS = [
    ("buy_entry", re.compile(r"\b(BUY|شراء)\s+([A-Z]{3,6}|ذهب|gold|oil|نفط)\b", re.IGNORECASE), "syntax_pattern", "forex"),
    ("sell_entry", re.compile(r"\b(SELL|بيع)\s+([A-Z]{3,6}|ذهب|gold|oil|نفط)\b", re.IGNORECASE), "syntax_pattern", "forex"),
    ("take_profit", re.compile(r"\b(TP\s*\d?|هدف\s*\d?|Target\s*\d?)\s*[:=\-]?\s*(\d+(?:\.\d+)?)", re.IGNORECASE), "syntax_pattern", "signals"),
    ("stop_loss", re.compile(r"\b(SL|Stop\s*Loss|وقف\s*خسار[ةه])\s*[:=\-]?\s*(\d+(?:\.\d+)?)", re.IGNORECASE), "syntax_pattern", "signals"),
    ("pips_gain", re.compile(r"\b(\+?\d+)\s*(pip|pips|نقط[ةه])\b", re.IGNORECASE), "syntax_pattern", "signals"),
    ("leverage", re.compile(r"\b(\d+x|\d+:\d+|رافعة\s*مالية)\b", re.IGNORECASE), "syntax_pattern", "crypto"),
    ("risk_reward", re.compile(r"\b(1\s*:\s*[2-9]|rr|r:r)\b", re.IGNORECASE), "syntax_pattern", "general_trading"),
]

# Known trading domains for channel mentions
DOMAIN_REGEX = re.compile(
    r"\b([a-zA-Z0-9_\-]+\.(?:tradingview\.com|exness\.com|binance\.com|bybit\.com|xm\.com|fxtm\.com|myfxbook\.com|forexfactory\.com))\b",
    re.IGNORECASE
)


class PatternMiner:
    """
    NLP & Contrastive Pattern Mining Engine.
    """

    @staticmethod
    def normalize_arabic(text: str) -> str:
        """
        Normalizes Arabic characters, strips diacritics, tatweel, and extra whitespace.
        """
        if not text:
            return ""

        # Remove Tashkeel (diacritics)
        tashkeel = re.compile(r"[\u064B-\u0652\u0670\u0640]")
        text = tashkeel.sub("", text)

        # Normalize Alefs
        text = re.sub(r"[إأآا]", "ا", text)
        # Normalize Teh Marbuta
        text = re.sub(r"ة", "ه", text)
        # Normalize Alef Maksura / Yaa
        text = re.sub(r"[ىي]", "ي", text)

        return text

    @classmethod
    def clean_text(cls, text: str) -> str:
        """
        Strips URLs, user handles, phone numbers, and normalizes text.
        """
        if not text:
            return ""

        # Remove URLs
        text = re.sub(r"https?://\S+|t\.me/\S+|www\.\S+", " ", text)
        # Remove mentions
        text = re.sub(r"@[a-zA-Z0-9_]+", " ", text)
        # Remove phone numbers
        text = re.sub(r"\+?\d[\d\s\-]{7,}\d", " ", text)

        # Normalize Arabic
        text = cls.normalize_arabic(text)

        # Remove non-alphanumeric except basic separators
        text = re.sub(r"[^\w\s\.\,\-\:\/]", " ", text)
        # Compress spaces
        text = re.sub(r"\s+", " ", text).strip()

        return text

    @classmethod
    def tokenize(cls, text: str) -> List[str]:
        """
        Tokenizes text into cleaned alphanumeric tokens, excluding stopwords and short tokens.
        """
        cleaned = cls.clean_text(text)
        raw_tokens = re.split(r"[\s\.\,\-\:\/\(\)\[\]]+", cleaned)
        tokens = []
        for t in raw_tokens:
            t_lower = t.lower()
            if len(t_lower) < 2:
                continue
            if t_lower in ARABIC_STOPWORDS or t_lower in ENGLISH_STOPWORDS:
                continue
            if t_lower in BLOCKED_IDENTIFIER_TOKENS:
                continue
            if re.match(r"^\d+$", t_lower):  # Pure numbers
                continue
            tokens.append(t_lower)
        return tokens

    @classmethod
    def extract_ngrams(cls, tokens: List[str], n: int) -> List[str]:
        """
        Extracts n-grams from token sequence.
        """
        if len(tokens) < n:
            return []
        return [" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]

    @classmethod
    def extract_symbols(cls, text: str) -> Set[str]:
        """
        Extracts trading symbols (e.g. XAUUSD, BTCUSDT, EURUSD).
        """
        symbols = set()
        matches = SYMBOL_REGEX.findall(text.upper())
        known_valid_prefixes = {
            "XAU", "EUR", "GBP", "USD", "JPY", "AUD", "CAD", "NZD", "CHF",
            "BTC", "ETH", "SOL", "XRP", "BNB", "ADA", "DOGE", "AVAX", "DOT",
            "US30", "NAS100", "SP500", "GER40", "UK100", "WTI", "BRENT"
        }
        for m in matches:
            clean_sym = m.replace("/", "")
            if len(clean_sym) < 3 or len(clean_sym) > 10:
                continue
            # Must start with or contain a known currency/crypto prefix
            if any(clean_sym.startswith(prefix) for prefix in known_valid_prefixes):
                symbols.add(clean_sym)
        return symbols

    @classmethod
    def extract_domains(cls, text: str) -> Set[str]:
        """
        Extracts trading and broker domains.
        """
        domains = set()
        for match in DOMAIN_REGEX.findall(text.lower()):
            domains.add(match)
        return domains

    @classmethod
    def extract_channel_features(cls, channel_doc: Dict[str, Any]) -> Dict[str, Set[str]]:
        """
        Extracts distinct features for a single channel across its title, about, and posts.
        Returns a dict of feature_type -> set of unique string values.
        """
        title = channel_doc.get("title", "") or ""
        about = channel_doc.get("about", "") or ""
        posts = channel_doc.get("posts", []) or []
        combined_text = f"{title} {about} " + " ".join(posts)

        tokens = cls.tokenize(combined_text)

        # 1. Unigrams
        unigrams = {t for t in tokens if len(t) >= 3}

        # 2. Bigrams
        bigrams = set(cls.extract_ngrams(tokens, 2))

        # 3. Trigrams
        trigrams = set(cls.extract_ngrams(tokens, 3))

        # 4. Symbols
        symbols = cls.extract_symbols(combined_text)

        # 5. Domains
        domains = cls.extract_domains(combined_text)

        # 6. Syntax patterns
        syntax = set()
        for name, pattern, sig_type, category in SYNTAX_PATTERNS:
            if pattern.search(combined_text):
                syntax.add(name)

        return {
            "keyword": unigrams,
            "phrase": bigrams.union(trigrams),
            "symbol": symbols,
            "domain": domains,
            "syntax_pattern": syntax
        }

    @classmethod
    def compute_log_odds_contrast(
        cls,
        df_pos: int,
        n_pos: int,
        df_neg: int,
        n_neg: int
    ) -> float:
        """
        Computes the log-odds ratio contrast with additive smoothing (0.5).
        Positive values indicate strong association with the Gold positive corpus.
        """
        if n_pos <= 0:
            return 0.0

        n_neg = max(1, n_neg)

        # Smoothed odds in positive corpus
        p_pos = (df_pos + 0.5) / (n_pos - df_pos + 0.5)
        # Smoothed odds in negative corpus
        p_neg = (df_neg + 0.5) / (n_neg - df_neg + 0.5)

        log_odds = math.log2(p_pos) - math.log2(p_neg)
        return round(log_odds, 3)

    @classmethod
    def categorize_signal(cls, signal_type: str, value: str) -> str:
        """
        Heuristic categorizer for mined signals.
        """
        val_lower = value.lower()
        if signal_type == "symbol":
            crypto_prefixes = {"btc", "eth", "sol", "xrp", "bnb", "ada", "doge", "avax", "dot"}
            if any(val_lower.startswith(p) for p in crypto_prefixes) or "usdt" in val_lower:
                return "crypto"
            if "xau" in val_lower or "gold" in val_lower:
                return "gold"
            return "forex"

        if any(w in val_lower for w in ["ذهب", "gold", "xau"]):
            return "gold"
        if any(w in val_lower for w in ["كريبتو", "crypto", "بيتكوين", "bitcoin", "binance", "bybit", "usdt"]):
            return "crypto"
        if any(w in val_lower for w in ["توصيات", "signals", "tp", "sl", "صفقات"]):
            return "signals"
        if any(w in val_lower for w in ["vip", "اداره محافظ", "إدارة محافظ", "نسخ", "حساب ممول", "وسيط", "broker"]):
            return "commercial"
        if any(w in val_lower for w in ["فوركس", "forex", "تداول", "عملات", "تحليل", "شارت"]):
            return "forex"

        return "general_trading"

    @classmethod
    def mine_and_score(
        cls,
        positive_corpus: List[Dict[str, Any]],
        negative_corpus: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Mines patterns from positive and negative corpora and calculates contrastive log-odds.
        Applies anti-overfitting rules:
        - Drops any feature with positive document frequency < 2.
        - Drops personal / channel-specific identifiers.
        """
        n_pos = len(positive_corpus)
        n_neg = len(negative_corpus)

        if n_pos == 0:
            logger.warning("[PATTERN_MINER] Positive corpus is empty. Cannot mine patterns.")
            return []

        logger.info(f"[PATTERN_MINER] Mining patterns from {n_pos} positive channels and {n_neg} negative channels.")

        # Document frequencies: (signal_type, feature) -> int
        df_pos: Dict[Tuple[str, str], int] = defaultdict(int)
        df_neg: Dict[Tuple[str, str], int] = defaultdict(int)

        # Provenance: (signal_type, feature) -> list of channel identifiers
        provenance: Dict[Tuple[str, str], List[str]] = defaultdict(list)
        evidence: Dict[Tuple[str, str], List[str]] = defaultdict(list)

        # 1. Process positive corpus
        for ch in positive_corpus:
            ch_name = ch.get("channel_username") or ch.get("channel_id") or "unknown_pos"
            features = cls.extract_channel_features(ch)
            for sig_type, feat_set in features.items():
                for feat in feat_set:
                    # Strip blocked personal tokens
                    if any(bt in feat for bt in BLOCKED_IDENTIFIER_TOKENS):
                        continue
                    key = (sig_type, feat)
                    df_pos[key] += 1
                    if len(provenance[key]) < 5:
                        provenance[key].append(str(ch_name))
                    if len(evidence[key]) < 3 and ch.get("title"):
                        evidence[key].append(f"Channel: {ch.get('title')}")

        # 2. Process negative corpus
        for ch in negative_corpus:
            features = cls.extract_channel_features(ch)
            for sig_type, feat_set in features.items():
                for feat in feat_set:
                    key = (sig_type, feat)
                    df_neg[key] += 1

        results = []

        for (sig_type, feat), pos_count in df_pos.items():
            # Anti-overfitting: MUST appear in at least 2 distinct positive channels
            if pos_count < 2:
                continue

            neg_count = df_neg.get((sig_type, feat), 0)
            contrast = cls.compute_log_odds_contrast(pos_count, n_pos, neg_count, n_neg)

            # Do not promote signals that have negative contrast (more common in spam)
            if contrast < 0.2:
                continue

            category = cls.categorize_signal(sig_type, feat)

            results.append({
                "signal_type": sig_type,
                "signal_value": feat,
                "normalized_value": cls.clean_text(feat),
                "category": category,
                "positive_support_count": pos_count,
                "negative_penalty_count": neg_count,
                "contrast_score": contrast,
                "provenance_sources": provenance.get((sig_type, feat), []),
                "evidence_samples": evidence.get((sig_type, feat), [])
            })

        # Sort by contrast score DESC then positive support count DESC
        results.sort(key=lambda x: (x["contrast_score"], x["positive_support_count"]), reverse=True)
        logger.info(f"[PATTERN_MINER] Mined {len(results)} valid signals passing anti-overfitting.")
        return results
