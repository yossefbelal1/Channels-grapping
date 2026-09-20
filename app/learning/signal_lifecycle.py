"""
app/learning/signal_lifecycle.py — Signal Lifecycle Management & State Machine

Manages state progression for discovered knowledge:
Observed -> Candidate -> Validated -> Active -> Deprecated
"""

import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class SignalStatus:
    OBSERVED = "observed"
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ALL = [OBSERVED, CANDIDATE, VALIDATED, ACTIVE, DEPRECATED]


class SignalType:
    KEYWORD = "keyword"
    PHRASE = "phrase"
    SYMBOL = "symbol"
    DOMAIN = "domain"
    SYNTAX_PATTERN = "syntax_pattern"
    NAMING_PATTERN = "naming_pattern"
    ALL = [KEYWORD, PHRASE, SYMBOL, DOMAIN, SYNTAX_PATTERN, NAMING_PATTERN]


class SignalLifecycle:
    """
    Evaluates evidence, support count, negative penalty, and contrast score
    to transition signals across lifecycle stages.
    """

    MIN_CANDIDATE_SUPPORT = 2
    MIN_VALIDATED_SUPPORT = 3
    MIN_VALIDATED_CONTRAST = 1.5
    MIN_ACTIVE_CONTRAST = 2.0
    MAX_NEGATIVE_RATIO_FOR_VALIDATED = 0.05
    DEPRECATION_NEGATIVE_RATIO = 0.15

    @classmethod
    def evaluate_status(
        cls,
        pos_support: int,
        neg_penalty: int,
        contrast_score: float,
        current_status: str = SignalStatus.OBSERVED
    ) -> str:
        """
        Calculates new lifecycle status based on multi-channel evidence and negative occurrences.
        """
        total_occurrences = pos_support + neg_penalty
        neg_ratio = (neg_penalty / total_occurrences) if total_occurrences > 0 else 0.0

        # Deprecation rule: high negative contamination
        if neg_penalty >= 2 and neg_ratio >= cls.DEPRECATION_NEGATIVE_RATIO:
            return SignalStatus.DEPRECATED

        # Active promotion rule: high multi-channel support + strong contrast + negligible negatives
        if (
            pos_support >= cls.MIN_VALIDATED_SUPPORT
            and contrast_score >= cls.MIN_ACTIVE_CONTRAST
            and neg_ratio <= cls.MAX_NEGATIVE_RATIO_FOR_VALIDATED
        ):
            return SignalStatus.ACTIVE

        # Validated rule
        if (
            pos_support >= cls.MIN_VALIDATED_SUPPORT
            and contrast_score >= cls.MIN_VALIDATED_CONTRAST
            and neg_ratio <= cls.MAX_NEGATIVE_RATIO_FOR_VALIDATED
        ):
            return SignalStatus.VALIDATED

        # Candidate rule: multi-channel support (>= 2 channels)
        if pos_support >= cls.MIN_CANDIDATE_SUPPORT and contrast_score >= 0.5 and neg_ratio < 0.10:
            return SignalStatus.CANDIDATE

        # Default fallback
        if current_status == SignalStatus.DEPRECATED and neg_ratio < 0.10 and pos_support >= cls.MIN_CANDIDATE_SUPPORT:
            return SignalStatus.CANDIDATE

        return SignalStatus.OBSERVED

    @classmethod
    def compute_confidence(cls, pos_support: int, neg_penalty: int, contrast_score: float) -> float:
        """
        Computes a bounded confidence score [0.0, 1.0].
        """
        if pos_support <= 0:
            return 0.0

        total = pos_support + neg_penalty
        support_factor = min(1.0, pos_support / 5.0)  # Maxes out at 5 distinct supporting channels
        purity_factor = 1.0 - (neg_penalty / total) if total > 0 else 1.0
        contrast_factor = max(0.0, min(1.0, contrast_score / 4.0))

        confidence = (support_factor * 0.4) + (purity_factor * 0.4) + (contrast_factor * 0.2)
        return round(min(1.0, max(0.0, confidence)), 3)

    @classmethod
    def upsert_signal(
        cls,
        db_conn,
        signal_type: str,
        signal_value: str,
        normalized_value: str,
        category: str,
        pos_support: int,
        neg_penalty: int,
        contrast_score: float,
        provenance: Optional[List[str]] = None,
        evidence: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Upserts a signal into discovered_signals in PostgreSQL with updated lifecycle and confidence.
        """
        if not db_conn or not signal_value:
            return None

        status = cls.evaluate_status(pos_support, neg_penalty, contrast_score)
        confidence = cls.compute_confidence(pos_support, neg_penalty, contrast_score)

        provenance_json = json.dumps(provenance or [])
        evidence_json = json.dumps(evidence or [])

        query = """
        INSERT INTO discovered_signals (
            signal_type, signal_value, normalized_value, category,
            status, confidence_score, contrast_score,
            positive_support_count, negative_penalty_count,
            provenance_sources, evidence_samples,
            created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s,
            %s::jsonb, %s::jsonb,
            NOW(), NOW()
        )
        ON CONFLICT (signal_type, signal_value) DO UPDATE SET
            normalized_value = EXCLUDED.normalized_value,
            category = EXCLUDED.category,
            status = EXCLUDED.status,
            confidence_score = EXCLUDED.confidence_score,
            contrast_score = EXCLUDED.contrast_score,
            positive_support_count = EXCLUDED.positive_support_count,
            negative_penalty_count = EXCLUDED.negative_penalty_count,
            provenance_sources = EXCLUDED.provenance_sources,
            evidence_samples = EXCLUDED.evidence_samples,
            updated_at = NOW()
        RETURNING id, signal_value, status, confidence_score, contrast_score;
        """
        try:
            with db_conn.cursor() as cur:
                cur.execute(query, (
                    signal_type, signal_value, normalized_value, category,
                    status, confidence, contrast_score,
                    pos_support, neg_penalty,
                    provenance_json, evidence_json
                ))
                row = cur.fetchone()
                db_conn.commit()
                if row:
                    if isinstance(row, dict):
                        return {
                            "id": row["id"],
                            "signal_value": row["signal_value"],
                            "status": row["status"],
                            "confidence_score": row["confidence_score"],
                            "contrast_score": row["contrast_score"]
                        }
                    return {
                        "id": row[0],
                        "signal_value": row[1],
                        "status": row[2],
                        "confidence_score": row[3],
                        "contrast_score": row[4]
                    }
        except Exception as e:
            logger.error(f"[LIFECYCLE] Error upserting signal '{signal_value}': {e}")
            try:
                db_conn.rollback()
            except Exception:
                pass
        return None
