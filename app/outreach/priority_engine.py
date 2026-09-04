"""
app/outreach/priority_engine.py — Commercial Fit & Outreach Priority Engine

Calculates explainable outreach priority (P0 to P4) using the multi-dimensional formula:
Forex Relevance (0-15) +
Commercial Fit (0-35) +
Business Model Strength (0-20) +
Operational Complexity (0-15) +
Audience Context (0-5) +
Freshness (0-5) +
Contactability (0-5)
= Outreach Priority Score (0-100)

Ranks pending campaign recipients so that active commercial businesses
with high service fit are contacted first.
"""

import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

from app.outreach.constants import OutreachPriority, ServiceNeedType
from app.outreach.commercial_inference import CommercialInferenceEngine

logger = logging.getLogger(__name__)


class OutreachPriorityEngine:
    """
    Computes priority rankings and service fit inferences for channels,
    and manages priority-based campaign ordering.
    """

    @classmethod
    def evaluate_priority(
        cls,
        title: str = "",
        description: str = "",
        recent_messages: Optional[List[Any]] = None,
        contacts_dict: Optional[Dict[str, Any]] = None,
        forex_relevance_score: int = 0,
        member_count: int = 0,
        posts_24h: int = 0,
        posts_7d: int = 0
    ) -> Dict[str, Any]:
        """
        Computes the complete commercial fit and outreach priority evaluation.
        """
        recent_messages = recent_messages or []
        contacts_dict = contacts_dict or {}

        # 1. Run Commercial Inference Engine
        comm_eval = CommercialInferenceEngine.analyze_channel_commercial_fit(
            title=title,
            description=description,
            recent_messages=recent_messages,
            contacts_dict=contacts_dict,
            posts_24h=posts_24h,
            posts_7d=posts_7d,
            member_count=member_count
        )

        comm_fit_pts = comm_eval["commercial_fit_score"]         # 0-35
        bm_pts = comm_eval["business_model_score"]                # 0-20
        op_pts = comm_eval["operational_complexity_score"]        # 0-15
        fresh_pts = comm_eval["freshness_score"]                  # 0-5

        # 2. Forex Relevance Points (0-15)
        # Scaled from 0-100 forex_relevance_score
        forex_pts = min(15, max(0, int(forex_relevance_score * 0.15)))

        # 3. Audience Context Points (0-5)
        # Context signal only: Never overrides business signals
        if member_count >= 100_000:
            audience_pts = 5
        elif member_count >= 10_000:
            audience_pts = 4
        elif member_count >= 1_000:
            audience_pts = 3
        elif member_count >= 300:
            audience_pts = 2
        else:
            audience_pts = 1

        # 4. Contactability Points (0-5)
        contact_pts = 0
        contact_user = contacts_dict.get("contact_username")
        contact_src = contacts_dict.get("source", "unknown")
        if contact_user:
            if contact_src in ("bio_official", "bio_admin", "intent_cta"):
                contact_pts = 5
            elif contact_src in ("bio_general", "message_keyword"):
                contact_pts = 4
            else:
                contact_pts = 3

        # 5. Calculate Total Priority Score (0-100)
        total_score = comm_fit_pts + bm_pts + op_pts + forex_pts + audience_pts + fresh_pts + contact_pts
        total_score = min(100, max(0, total_score))

        # 6. Assign Priority Tier (P0 to P4)
        has_clear_business_model = len(comm_eval["detected_models"]) >= 1
        has_high_commercial_activity = comm_fit_pts >= 18
        has_contact = contact_pts >= 3

        if total_score >= 70 and has_clear_business_model and has_contact:
            tier = OutreachPriority.P0
            tier_label = "P0 (Immediate Commercial Priority)"
        elif total_score >= 55 and (has_clear_business_model or has_high_commercial_activity):
            tier = OutreachPriority.P1
            tier_label = "P1 (Very High Commercial Fit)"
        elif total_score >= 38 and (has_clear_business_model or comm_fit_pts >= 10 or forex_pts >= 8):
            tier = OutreachPriority.P2
            tier_label = "P2 (High Relevance Business Channel)"
        elif total_score >= 18 or forex_pts >= 8:
            tier = OutreachPriority.P3
            tier_label = "P3 (Normal Forex / Educational / News Channel)"
        else:
            tier = OutreachPriority.P4
            tier_label = "P4 (Low Commercial Fit)"

        # 7. Generate Explainable Reason
        models_str = ", ".join(comm_eval["detected_models"]) if comm_eval["detected_models"] else "general trading"
        services_str = ", ".join(comm_eval["likely_services"]) if comm_eval["likely_services"] else "general outreach"

        if tier == OutreachPriority.P0:
            reason = f"High-confidence commercial business operating {models_str} with active monetization CTAs. Recommended for: {services_str}."
        elif tier == OutreachPriority.P1:
            reason = f"Strong commercial signals detected ({models_str}). High potential service fit for {services_str}."
        elif tier == OutreachPriority.P2:
            reason = f"Relevant Forex business channel with moderate commercial activity ({models_str})."
        elif tier == OutreachPriority.P3:
            reason = f"Relevant Forex channel primarily offering informational/signals content without clear monetization."
        else:
            reason = f"Minimal commercial signals or low business activity."

        return {
            "priority": tier,
            "priority_tier_label": tier_label,
            "priority_score": total_score,
            "reason": reason,
            "commercial_fit_score": comm_fit_pts,
            "business_model_score": bm_pts,
            "operational_complexity_score": op_pts,
            "forex_relevance_score": forex_pts,
            "audience_context_score": audience_pts,
            "freshness_score": fresh_pts,
            "contactability_score": contact_pts,
            "detected_models": comm_eval["detected_models"],
            "likely_services": comm_eval["likely_services"],
            "confidence": comm_eval["confidence"],
            "freshness_days": comm_eval["freshness_days"],
            "freshest_commercial_date": comm_eval.get("freshest_commercial_date"),
            "evidence": {
                "detected_models": comm_eval["detected_models"],
                "promo_post_count": comm_eval["promo_post_count"],
                "payment_methods": comm_eval["payment_methods"],
                "has_structured_signals": comm_eval["has_structured_signals"],
                "likely_services": comm_eval["likely_services"],
                "contact_source": contact_src,
                "freshness_days": comm_eval["freshness_days"],
                "snippets": comm_eval["evidence_snippets"]
            }
        }

    @classmethod
    def rerank_campaign_recipients(cls, db_conn, campaign_id: str) -> Dict[str, int]:
        """
        Re-ranks all pending recipients in a campaign by synchronizing the latest
        priority scores from the leads table into campaign_logs.
        Returns a breakdown count of recipients per tier.
        """
        if not db_conn or not campaign_id:
            return {}

        counts = {OutreachPriority.P0: 0, OutreachPriority.P1: 0, OutreachPriority.P2: 0, OutreachPriority.P3: 0, OutreachPriority.P4: 0}
        try:
            with db_conn.cursor() as cur:
                # Update campaign_logs from current leads commercial intelligence
                cur.execute("""
                    UPDATE campaign_logs cl
                    SET priority = COALESCE(l.outreach_priority, 'P3'),
                        priority_score = COALESCE(l.outreach_priority_score, 25),
                        priority_reason = l.outreach_priority_reason,
                        intent_type = l.commercial_intent_type,
                        intent_evidence = l.commercial_intent_evidence
                    FROM leads l
                    WHERE cl.lead_id = l.id
                      AND cl.campaign_id = %s
                      AND cl.status = 'pending';
                """, (campaign_id,))
                updated_count = cur.rowcount

                # Query updated tier breakdown
                cur.execute("""
                    SELECT COALESCE(priority, 'P3') as p_tier, COUNT(*) as cnt
                    FROM campaign_logs
                    WHERE campaign_id = %s AND status = 'pending'
                    GROUP BY priority;
                """, (campaign_id,))

                for row in cur.fetchall():
                    tier = row[0] if isinstance(row, tuple) else (row.get('p_tier') or row.get('priority'))
                    c = row[1] if isinstance(row, tuple) else (row.get('cnt') or row.get('count', 0))
                    if tier in counts:
                        counts[tier] = c

            db_conn.commit()
            logger.info(f"Re-ranked campaign {campaign_id} recipients: {counts}")
            return {
                "success": True,
                "campaign_id": campaign_id,
                "updated": updated_count,
                "tier_counts": counts,
                **counts
            }
        except Exception as err:
            logger.error(f"Error re-ranking campaign {campaign_id}: {err}")
            try:
                db_conn.rollback()
            except Exception:
                pass
            return {"success": False, "error": str(err), "updated": 0, "tier_counts": counts}
