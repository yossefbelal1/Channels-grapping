"""
app/outreach/priority_engine.py — Exchange Network Fit & Campaign Priority Engine

Calculates explainable outreach priority (P0 to P4) using the Exchange Network Node formula:
Forex Relevance (30%) +
Exchange Affinity (35%) +
Small/Mid Size Sweet Spot (20%) +
Contactability (15%)
= Outreach Priority Score (0-100)

Ranks pending campaign recipients so that active small and mid-sized trading channels
with high cross-promotion and exchange affinity are contacted first.
"""

import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

from app.outreach.constants import OutreachPriority, ServiceNeedType
from app.outreach.commercial_inference import CommercialInferenceEngine
from app.discovery.exchange_analyzer import ExchangeAffinityAnalyzer

logger = logging.getLogger(__name__)


class OutreachPriorityEngine:
    """
    Computes priority rankings for channels in the Cross-Promotion Network,
    prioritizing small and medium channels with strong exchange affinity and verified contacts.
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
        posts_7d: int = 0,
        in_degree: int = 0,
        out_degree: int = 0,
        relation_types: Optional[set] = None
    ) -> Dict[str, Any]:
        """
        Computes the complete exchange network node evaluation and outreach priority.
        """
        recent_messages = recent_messages or []
        contacts_dict = contacts_dict or {}

        contact_user = contacts_dict.get("contact_username")
        contact_src = contacts_dict.get("source", "unknown")
        has_contact = bool(contact_user and str(contact_user).strip())

        # 1. Run Exchange Affinity & Network Value Analyzer
        exchange_eval = ExchangeAffinityAnalyzer.analyze_exchange_affinity(
            title=title,
            description=description,
            recent_messages=recent_messages,
            member_count=member_count,
            contact_username=contact_user,
            has_verified_contact=has_contact,
            in_degree=in_degree,
            out_degree=out_degree,
            relation_types=relation_types,
            forex_relevance_score=forex_relevance_score
        )

        exchange_affinity = exchange_eval["exchange_affinity_score"]  # 0-100
        size_sweet_spot = exchange_eval["growth_openness_score"]     # 0-100 (peaks at 1k-35k)
        network_val = exchange_eval["network_value_score"]          # 0-100
        is_seed = exchange_eval["is_exchange_seed"]
        is_hub = exchange_eval["is_exchange_hub"]

        # 2. Run Commercial Inference Engine (retained for backward compatibility and auxiliary context)
        comm_eval = CommercialInferenceEngine.analyze_channel_commercial_fit(
            title=title,
            description=description,
            recent_messages=recent_messages,
            contacts_dict=contacts_dict,
            posts_24h=posts_24h,
            posts_7d=posts_7d,
            member_count=member_count
        )
        comm_fit_pts = comm_eval.get("commercial_fit_score", 0)
        has_clear_business_model = len(comm_eval.get("detected_models", [])) >= 1

        # 3. Contactability Points (0-5 scale for backward compatibility, mapped to 0-100 internally)
        if has_contact:
            if contact_src in ("bio_official", "bio_admin", "intent_cta", "pinned_msg"):
                contact_pts_5 = 5
            elif contact_src in ("bio_general", "message_keyword", "deep_pinned_scan"):
                contact_pts_5 = 4
            else:
                contact_pts_5 = 3
        else:
            contact_pts_5 = 0

        contact_pts_100 = contact_pts_5 * 20

        # 4. Composite Network Priority Score (0-100)
        # Combines exchange network fitness and commercial fitness
        exchange_component = (
            (forex_relevance_score * 0.30) +
            (exchange_affinity * 0.35) +
            (size_sweet_spot * 0.20) +
            (contact_pts_100 * 0.15)
        )
        commercial_component = (
            comm_fit_pts +
            comm_eval.get("business_model_score", 0) +
            comm_eval.get("operational_complexity_score", 0) +
            min(15, int(forex_relevance_score * 0.15)) +
            (3 if member_count >= 10000 else (2 if member_count >= 1000 else 1)) +
            comm_eval.get("freshness_score", 0) +
            contact_pts_5
        )

        raw_composite = max(exchange_component, commercial_component)

        if is_hub:
            raw_composite += 10
        if network_val >= 40:
            raw_composite += 5

        total_score = max(0, min(100, int(round(raw_composite))))

        # 5. Assign Priority Tier (P0 to P4)
        # P0: Prime Exchange Partner / Prime Commercial Business
        # Genuine trading channel (forex >= 20) + verified contact + (strong exchange fit OR strong commercial fit)
        is_p0 = (
            forex_relevance_score >= 20
            and has_contact
            and (
                (exchange_affinity >= 35 and size_sweet_spot >= 55)
                or (total_score >= 65 and size_sweet_spot >= 50)
                or (is_seed and total_score >= 60)
                or (total_score >= 70 and has_clear_business_model)
            )
        )

        # P1: High-Value Exchange Node / Very High Commercial Fit
        is_p1 = (
            not is_p0
            and forex_relevance_score >= 20
            and has_contact
            and (
                total_score >= 50
                or (exchange_affinity >= 25 and size_sweet_spot >= 45)
                or (network_val >= 35)
                or (has_clear_business_model and total_score >= 45)
            )
        )

        # P2: Standard Candidate
        # Channels without contact CANNOT be P0, P1, or P2
        is_p2 = (
            not is_p0 and not is_p1
            and has_contact
            and (forex_relevance_score >= 25 or comm_fit_pts >= 10)
            and total_score >= 32
        )

        # P3: Informational / News / Oversized / Missing Contact
        is_p3 = (
            not is_p0 and not is_p1 and not is_p2
            and (total_score >= 18 or forex_relevance_score >= 20)
        )

        if is_p0:
            tier = OutreachPriority.P0
            tier_label = "P0 (Prime Exchange Partner - Small/Mid Sweet Spot)"
        elif is_p1:
            tier = OutreachPriority.P1
            tier_label = "P1 (High-Value Exchange Node)"
        elif is_p2:
            tier = OutreachPriority.P2
            tier_label = "P2 (Standard Candidate)"
        elif is_p3:
            tier = OutreachPriority.P3
            tier_label = "P3 (Informational / Oversized / Low Evidence)"
        else:
            tier = OutreachPriority.P4
            tier_label = "P4 (Low Fit / Noise)"

        # 6. Generate Explainable Reason
        size_label = exchange_eval["evidence"].get("size_bracket", "")
        peer_cnt = exchange_eval["evidence"].get("distinct_peer_count", 0)

        if tier == OutreachPriority.P0:
            reason = f"Prime Exchange Partner: High trading fit ({forex_relevance_score}%), optimal size ({size_label}), verified contact (@{contact_user}), and strong exchange affinity ({exchange_affinity}% with {peer_cnt} peer links)."
        elif tier == OutreachPriority.P1:
            reason = f"High-Value Exchange Node: Relevant trading channel with active network relations ({peer_cnt} peers, {network_val}% net value) and verified contact."
        elif tier == OutreachPriority.P2:
            reason = f"Relevant trading channel with moderate exchange potential ({size_label})."
        elif tier == OutreachPriority.P3:
            reason = f"Trading channel primarily offering informational/news content without active exchange readiness."
        else:
            reason = f"Low exchange network suitability or minimal trading signals."

        evidence_payload = {
            "detected_models": comm_eval.get("detected_models", []),
            "promo_post_count": comm_eval.get("promo_post_count", 0),
            "payment_methods": comm_eval.get("payment_methods", []),
            "has_structured_signals": comm_eval.get("has_structured_signals", False),
            "likely_services": comm_eval.get("likely_services", []),
            "contact_source": contact_src,
            "freshness_days": comm_eval.get("freshness_days"),
            "snippets": comm_eval.get("evidence_snippets", []),
            "exchange_network_analysis": exchange_eval["evidence"]
        }

        return {
            "priority": tier,
            "priority_tier_label": tier_label,
            "priority_score": total_score,
            "reason": reason,
            "exchange_affinity_score": exchange_affinity,
            "growth_openness_score": size_sweet_spot,
            "network_value_score": network_val,
            "is_exchange_seed": is_seed,
            "is_exchange_hub": is_hub,
            "contactability_score": contact_pts_5,
            "exchange_evidence": exchange_eval["evidence"],
            "commercial_fit_score": comm_fit_pts,
            "business_model_score": comm_eval.get("business_model_score", 0),
            "operational_complexity_score": comm_eval.get("operational_complexity_score", 0),
            "forex_relevance_score": forex_relevance_score,
            "audience_context_score": 3 if member_count >= 10000 else (2 if member_count >= 1000 else 1),
            "freshness_score": comm_eval.get("freshness_score", 0),
            "detected_models": comm_eval.get("detected_models", []),
            "likely_services": ["Cross-Promotion", "Channel Exchange", "Mutual Shoutout"] + comm_eval.get("likely_services", []),
            "confidence": comm_eval.get("confidence", 80),
            "freshness_days": comm_eval.get("freshness_days"),
            "freshest_commercial_date": comm_eval.get("freshest_commercial_date"),
            "evidence": evidence_payload
        }

    @classmethod
    def rerank_campaign_recipients(cls, db_conn, campaign_id: str) -> Dict[str, Any]:
        """
        Re-ranks all pending recipients in a campaign by synchronizing latest
        priority scores from leads into campaign_logs.
        """
        if not db_conn or not campaign_id:
            return {}

        counts = {
            OutreachPriority.P0: 0,
            OutreachPriority.P1: 0,
            OutreachPriority.P2: 0,
            OutreachPriority.P3: 0,
            OutreachPriority.P4: 0,
            OutreachPriority.PENDING: 0
        }
        try:
            with db_conn.cursor() as cur:
                cur.execute("""
                    UPDATE campaign_logs cl
                    SET priority = COALESCE(l.outreach_priority, 'PENDING'),
                        priority_score = COALESCE(l.outreach_priority_score, 0),
                        priority_reason = COALESCE(l.outreach_priority_reason, 'Pending evaluation'),
                        intent_type = l.commercial_intent_type,
                        intent_evidence = COALESCE(l.exchange_evidence, l.commercial_evidence)
                    FROM leads l
                    WHERE cl.lead_id = l.id
                      AND cl.campaign_id = %s
                      AND cl.status IN ('pending', 'pending_review', 'approved');
                """, (campaign_id,))
                updated_count = cur.rowcount

                cur.execute("""
                    SELECT COALESCE(priority, 'PENDING') as p_tier, COUNT(*) as cnt
                    FROM campaign_logs
                    WHERE campaign_id = %s AND status IN ('pending', 'pending_review', 'approved')
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
