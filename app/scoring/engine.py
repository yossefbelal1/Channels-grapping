"""
app/scoring/engine.py — Production Lead Scoring Engine with Two-Stage Evaluation
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from app.scoring.dimensions import ScoringDimensions, calculate_all_dimensions

logger = logging.getLogger(__name__)


class LeadScoringEngine:
    """
    Orchestrates two-stage lead evaluation, multi-dimensional scoring,
    and PostgreSQL persistence for all discovered channels.
    """

    def __init__(self, db_conn=None):
        self.db = db_conn

    @staticmethod
    def evaluate_stage_1(
        title: str,
        description: str,
        username: str,
        member_count: int = 0
    ) -> Tuple[bool, str, int]:
        """
        Stage 1: Cheap Validation (Metadata only).
        Rejects obvious non-trading spam or system entities before expensive message scraping.
        Note: NEVER rejects based solely on low member count.
        
        Returns:
            Tuple of (is_promising: bool, reason: str, preliminary_score: int)
        """
        combined = f"{title} {description} {username}".lower()

        # Reject bot usernames or reserved paths
        if username.endswith("bot") or username.endswith("_bot"):
            return False, "Bot entity", 0

        # Run lightweight taxonomy check
        from app.discovery.taxonomy import classify_text_taxonomy
        tax_hits = classify_text_taxonomy(combined)
        total_hits = sum(tax_hits.values())

        if total_hits >= 1:
            return True, "Passed Stage 1 with relevant trading keywords", min(100, total_hits * 25)

        # Retain channels with high Arabic density and trading-related title
        from app.discovery.arabic_normalizer import calculate_arabic_letter_ratio
        if calculate_arabic_letter_ratio(combined) > 0.4 and ("vip" in combined or "channel" in combined or "تداول" in combined):
            return True, "Passed Stage 1 on Arabic community pattern", 40

        # If zero trading indicators are found even in title/bio
        return True, "Candidate queued for Stage 2 deep message sampling", 20

    @staticmethod
    def evaluate_stage_2(
        title: str = "",
        description: str = "",
        recent_posts: Optional[List[str]] = None,
        member_count: int = 0,
        has_contact: bool = False,
        contact_types: Optional[List[str]] = None,
        discovery_count: int = 1,
        first_seen_at=None,
        last_post_at=None,
        posts_24h: int = 0,
        posts_7d: int = 0,
        posts_30d: int = 0,
        creation_date=None,
        is_group: bool = False
    ) -> ScoringDimensions:
        """
        Stage 2: Deep Validation & Multi-Dimensional Scoring.
        Processes post content, signals, contacts, and temporal activity metrics.
        """
        return calculate_all_dimensions(
            title=title,
            description=description,
            recent_posts=recent_posts,
            member_count=member_count,
            has_contact=has_contact,
            contact_types=contact_types,
            discovery_count=discovery_count,
            first_seen_at=first_seen_at,
            last_post_at=last_post_at,
            posts_24h=posts_24h,
            posts_7d=posts_7d,
            posts_30d=posts_30d,
            creation_date=creation_date,
            is_group=is_group
        )

    def persist_scores_to_db(self, channel_id: str, scores: ScoringDimensions) -> None:
        """Saves all 13 scoring dimensions and tier to the leads table in PostgreSQL."""
        if not self.db or not channel_id:
            return

        try:
            with self.db.cursor() as cur:
                cur.execute("""
                    UPDATE leads
                    SET lead_score = %s,
                        tier = %s::tier_level,
                        forex_score = %s,
                        arabic_ratio = %s,
                        trading_score = %s,
                        signal_score = %s,
                        gold_score = %s,
                        activity_score = %s,
                        growth_score = %s,
                        commercial_score = %s,
                        contact_score = %s,
                        legitimacy_score = %s,
                        discovery_score = %s,
                        new_channel_score = %s
                    WHERE id = %s;
                """, (
                    scores.final_score,
                    scores.tier,
                    scores.forex_score,
                    scores.arabic_score,
                    scores.trading_score,
                    scores.signal_score,
                    scores.gold_score,
                    scores.activity_score,
                    scores.growth_score,
                    scores.commercial_score,
                    scores.contact_score,
                    scores.legitimacy_score,
                    scores.discovery_score,
                    scores.new_channel_score,
                    channel_id
                ))
            self.db.commit()
        except Exception as db_err:
            logger.warning(f"Failed to persist lead scores in DB for {channel_id}: {db_err}")
            try:
                self.db.rollback()
            except Exception:
                pass
