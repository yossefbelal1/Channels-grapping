"""
app/learning/knowledge_model.py — In-Memory & Redis Cached Knowledge Model

Provides fast O(1) lookups for active learned signals, confidence scores,
dynamic relevance boost evaluation, and cross-worker synchronization.
"""

import json
import logging
from typing import Dict, Any, List, Set, Tuple, Optional
from datetime import datetime, timezone

from app.learning.signal_lifecycle import SignalStatus, SignalType
from app.learning.pattern_miner import PatternMiner

logger = logging.getLogger(__name__)

REDIS_MODEL_KEY = "signals:active:model"
MODEL_CACHE_TTL = 3600  # 1 hour


class KnowledgeModel:
    """
    In-memory representation of learned trading signals and patterns.
    """

    def __init__(self):
        self.active_keywords: Set[str] = set()
        self.active_phrases: Set[str] = set()
        self.active_symbols: Set[str] = set()
        self.active_domains: Set[str] = set()
        self.active_syntax: Set[str] = set()

        self.candidate_phrases: Set[str] = set()
        self.candidate_keywords: Set[str] = set()

        # Signal details: (signal_type, signal_value) -> dict of metadata
        self.signals_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.last_synced_at: Optional[datetime] = None

    def load_from_db(self, db_conn) -> bool:
        """
        Loads active, validated, and candidate signals from PostgreSQL.
        """
        if not db_conn:
            logger.warning("[KNOWLEDGE_MODEL] Cannot load from DB: db_conn is None.")
            return False

        query = """
        SELECT signal_type, signal_value, normalized_value, category,
               status, confidence_score, contrast_score, positive_support_count,
               discovery_count
        FROM discovered_signals
        WHERE status IN ('active', 'validated', 'candidate')
        ORDER BY confidence_score DESC, contrast_score DESC;
        """
        try:
            with db_conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()

                self._clear()

                for r in rows:
                    if isinstance(r, dict):
                        sig_type = r["signal_type"]
                        sig_val = r["signal_value"]
                        norm_val = r["normalized_value"]
                        category = r.get("category")
                        status = r["status"]
                        conf = float(r.get("confidence_score") or 0.5)
                        contrast = float(r.get("contrast_score") or 0.0)
                        pos_count = int(r.get("positive_support_count") or 1)
                        disc_count = int(r.get("discovery_count") or 0)
                    else:
                        sig_type = r[0]
                        sig_val = r[1]
                        norm_val = r[2]
                        category = r[3]
                        status = r[4]
                        conf = float(r[5] or 0.5)
                        contrast = float(r[6] or 0.0)
                        pos_count = int(r[7] or 1)
                        disc_count = int(r[8] or 0)

                    sig_info = {
                        "signal_type": sig_type,
                        "signal_value": sig_val,
                        "normalized_value": norm_val,
                        "category": category,
                        "status": status,
                        "confidence_score": conf,
                        "contrast_score": contrast,
                        "positive_support_count": pos_count,
                        "discovery_count": disc_count
                    }

                    self.signals_map[(sig_type, sig_val)] = sig_info

                    if status in (SignalStatus.ACTIVE, SignalStatus.VALIDATED):
                        if sig_type == SignalType.KEYWORD:
                            self.active_keywords.add(norm_val)
                        elif sig_type == SignalType.PHRASE:
                            self.active_phrases.add(norm_val)
                        elif sig_type == SignalType.SYMBOL:
                            self.active_symbols.add(sig_val.upper())
                        elif sig_type == SignalType.DOMAIN:
                            self.active_domains.add(norm_val.lower())
                        elif sig_type == SignalType.SYNTAX_PATTERN:
                            self.active_syntax.add(sig_val)

                    elif status == SignalStatus.CANDIDATE:
                        if sig_type == SignalType.KEYWORD:
                            self.candidate_keywords.add(norm_val)
                        elif sig_type == SignalType.PHRASE:
                            self.candidate_phrases.add(norm_val)

                self.last_synced_at = datetime.now(timezone.utc)
                logger.info(
                    f"[KNOWLEDGE_MODEL] Synced from DB: {len(self.active_keywords)} keywords, "
                    f"{len(self.active_phrases)} phrases, {len(self.active_symbols)} symbols, "
                    f"{len(self.candidate_phrases)} candidate phrases."
                )
                return True
        except Exception as e:
            logger.error(f"[KNOWLEDGE_MODEL] Error loading signals from DB: {e}")
            return False

    def sync_to_redis(self, redis_client) -> bool:
        """
        Serializes and caches the active knowledge model in Redis for fast worker sync.
        """
        if not redis_client:
            return False

        try:
            payload = {
                "active_keywords": list(self.active_keywords),
                "active_phrases": list(self.active_phrases),
                "active_symbols": list(self.active_symbols),
                "active_domains": list(self.active_domains),
                "active_syntax": list(self.active_syntax),
                "candidate_keywords": list(self.candidate_keywords),
                "candidate_phrases": list(self.candidate_phrases),
                "synced_at": datetime.now(timezone.utc).isoformat()
            }
            redis_client.setex(REDIS_MODEL_KEY, MODEL_CACHE_TTL, json.dumps(payload))
            return True
        except Exception as e:
            logger.error(f"[KNOWLEDGE_MODEL] Failed to sync to Redis: {e}")
            return False

    def load_from_redis(self, redis_client) -> bool:
        """
        Loads the active knowledge model from Redis cache if available.
        """
        if not redis_client:
            return False

        try:
            data = redis_client.get(REDIS_MODEL_KEY)
            if not data:
                return False

            payload = json.loads(data)
            self._clear()

            self.active_keywords = set(payload.get("active_keywords", []))
            self.active_phrases = set(payload.get("active_phrases", []))
            self.active_symbols = set(payload.get("active_symbols", []))
            self.active_domains = set(payload.get("active_domains", []))
            self.active_syntax = set(payload.get("active_syntax", []))
            self.candidate_keywords = set(payload.get("candidate_keywords", []))
            self.candidate_phrases = set(payload.get("candidate_phrases", []))

            self.last_synced_at = datetime.now(timezone.utc)
            return True
        except Exception as e:
            logger.error(f"[KNOWLEDGE_MODEL] Error loading from Redis: {e}")
            return False

    def evaluate_text_boost(self, text: str) -> Tuple[float, List[str]]:
        """
        Evaluates text (title, bio, posts) against active learned signals.
        Returns (boost_points, matched_signals_list).
        Max boost is capped at +20 points.
        """
        if not text:
            return 0.0, []

        norm_text = PatternMiner.clean_text(text)
        tokens = set(PatternMiner.tokenize(norm_text))
        matched = []
        boost = 0.0

        # 1. Match Active Symbols (+4 pts each, up to +12)
        symbols = PatternMiner.extract_symbols(text)
        matched_symbols = symbols.intersection(self.active_symbols)
        for s in matched_symbols:
            boost += 4.0
            matched.append(f"symbol:{s}")

        # 2. Match Active Phrases (+5 pts each, up to +15)
        for phrase in self.active_phrases:
            if phrase in norm_text:
                boost += 5.0
                matched.append(f"phrase:{phrase}")
                if boost >= 20.0:
                    break

        # 3. Match Active Keywords (+2 pts each)
        matched_kw = tokens.intersection(self.active_keywords)
        for kw in matched_kw:
            boost += 2.0
            matched.append(f"kw:{kw}")
            if boost >= 20.0:
                break

        # Cap boost between 0.0 and 20.0
        final_boost = min(20.0, max(0.0, boost))
        return round(final_boost, 1), matched

    @staticmethod
    def increment_discovery_yield(db_conn, signal_value: str) -> None:
        """
        Increments discovery_count and updates last_yielded_at when a signal yields a valid lead.
        """
        if not db_conn or not signal_value:
            return

        query = """
        UPDATE discovered_signals
        SET discovery_count = discovery_count + 1,
            last_yielded_at = NOW(),
            confidence_score = LEAST(1.0, confidence_score + 0.02),
            updated_at = NOW()
        WHERE signal_value = %s;
        """
        try:
            with db_conn.cursor() as cur:
                cur.execute(query, (signal_value,))
                db_conn.commit()
        except Exception as e:
            logger.error(f"[KNOWLEDGE_MODEL] Failed to increment discovery yield for '{signal_value}': {e}")
            try:
                db_conn.rollback()
            except Exception:
                pass

    def _clear(self):
        self.active_keywords.clear()
        self.active_phrases.clear()
        self.active_symbols.clear()
        self.active_domains.clear()
        self.active_syntax.clear()
        self.candidate_keywords.clear()
        self.candidate_phrases.clear()
        self.signals_map.clear()
