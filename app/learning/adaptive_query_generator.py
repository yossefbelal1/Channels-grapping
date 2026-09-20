"""
app/learning/adaptive_query_generator.py — 80/20 Exploitation & Exploration Query Generator

Generates high-yield Telegram search queries for worker_scavenger dynamically:
- 80% Exploitation: Top active trading phrases, high-confidence asset pair combinations.
- 20% Exploration: Candidate n-grams, emerging transliterations, and exploratory combinations.
"""

import random
import logging
from typing import Dict, Any, List, Set, Optional

from app.learning.knowledge_model import KnowledgeModel

logger = logging.getLogger(__name__)

# Fallback queries if knowledge model is empty or bootstrapping
FALLBACK_QUERIES = [
    "توصيات فوركس vip",
    "تداول الذهب xauusd",
    "صفقات كريبتو binance",
    "تحليل فني عملات",
    "ادارة محافظ فوركس",
    "توصيات مجانية vip",
    "forex signals arabic",
    "crypto scalping ar",
    "تداول البيتكوين btc",
    "نسخ صفقات forex"
]


class AdaptiveQueryGenerator:
    """
    Dynamically generates discovery search queries using the KnowledgeModel.
    """

    @classmethod
    def generate_queries(
        cls,
        model: Optional[KnowledgeModel],
        count: int = 10,
        exploit_ratio: float = 0.8
    ) -> List[Dict[str, Any]]:
        """
        Generates `count` search queries using 80% exploitation and 20% exploration.
        """
        if not model or (not model.active_phrases and not model.active_symbols and not model.active_keywords):
            logger.info("[QUERY_GEN] KnowledgeModel empty or not ready; using fallback queries.")
            return [
                {
                    "query": q,
                    "strategy": "fallback",
                    "source_signals": []
                }
                for q in random.sample(FALLBACK_QUERIES, min(count, len(FALLBACK_QUERIES)))
            ]

        exploit_count = int(round(count * exploit_ratio))
        explore_count = count - exploit_count

        queries: List[Dict[str, Any]] = []
        seen_queries: Set[str] = set()

        # 1. Exploitation Queries (80%)
        # Strategy A: Active Phrases directly
        active_phrases_list = list(model.active_phrases)
        random.shuffle(active_phrases_list)
        for phrase in active_phrases_list:
            if len(queries) >= exploit_count:
                break
            q = phrase.strip()
            if q and q not in seen_queries and len(q.split()) <= 4:
                queries.append({
                    "query": q,
                    "strategy": "exploit",
                    "source_signals": [phrase]
                })
                seen_queries.add(q)

        # Strategy B: Active Symbol + Active Keyword / Anchor
        active_symbols_list = list(model.active_symbols)
        active_kw_list = list(model.active_keywords)
        random.shuffle(active_symbols_list)
        random.shuffle(active_kw_list)

        while len(queries) < exploit_count and active_symbols_list and active_kw_list:
            sym = random.choice(active_symbols_list)
            kw = random.choice(active_kw_list)
            q = f"{sym} {kw}".strip()
            if q not in seen_queries:
                queries.append({
                    "query": q,
                    "strategy": "exploit",
                    "source_signals": [sym, kw]
                })
                seen_queries.add(q)
            if len(seen_queries) > 50:  # Prevent infinite loop
                break

        # 2. Exploration Queries (20%)
        # Strategy C: Candidate Phrases & Candidate Keywords
        candidate_phrases_list = list(model.candidate_phrases)
        candidate_kw_list = list(model.candidate_keywords)
        random.shuffle(candidate_phrases_list)
        random.shuffle(candidate_kw_list)

        target_total = exploit_count + explore_count
        for phrase in candidate_phrases_list:
            if len(queries) >= target_total:
                break
            q = phrase.strip()
            if q and q not in seen_queries and len(q.split()) <= 4:
                queries.append({
                    "query": q,
                    "strategy": "explore",
                    "source_signals": [phrase]
                })
                seen_queries.add(q)

        # Strategy D: Candidate Keyword + Random Active Symbol
        while len(queries) < target_total and candidate_kw_list and active_symbols_list:
            ckw = random.choice(candidate_kw_list)
            sym = random.choice(active_symbols_list)
            q = f"{sym} {ckw}".strip()
            if q not in seen_queries:
                queries.append({
                    "query": q,
                    "strategy": "explore",
                    "source_signals": [sym, ckw]
                })
                seen_queries.add(q)
            if len(seen_queries) > 50:
                break

        # If we still need queries, fill with fallback
        if len(queries) < count:
            for fallback in FALLBACK_QUERIES:
                if len(queries) >= count:
                    break
                if fallback not in seen_queries:
                    queries.append({
                        "query": fallback,
                        "strategy": "fallback",
                        "source_signals": []
                    })
                    seen_queries.add(fallback)

        return queries[:count]
