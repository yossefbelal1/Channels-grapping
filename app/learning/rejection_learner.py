"""
app/learning/rejection_learner.py — Interactive Rejection Learning & Anti-Pattern Extractor

When a user rejects or cancels a channel from the review page or CRM:
1. Cancels/removes the lead from active campaign logs so no outreach message is sent.
2. Marks the lead as 'rejected' with the user's feedback reason.
3. Harvests the channel's title, bio, and sample posts into `corpus_channels` as 'negative_spam'.
4. Extracts n-grams, keywords, and structural patterns via `PatternMiner`.
5. Promotes learned negative signals into `discovered_signals` and Redis sets.
6. Synchronizes with `KnowledgeModel` and `RelevanceEvaluator` to immediately downvote
   or disqualify future candidates with similar content.
"""

import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

from app.learning.pattern_miner import PatternMiner
from app.learning.signal_lifecycle import SignalStatus, SignalType

logger = logging.getLogger(__name__)

REDIS_NEG_KEYWORDS_KEY = "signals:negative:keywords"
REDIS_NEG_PHRASES_KEY = "signals:negative:phrases"


class RejectionLearner:
    """
    Processes user channel rejections, cancels campaign outreach, and extracts
    negative learning patterns to prevent similar junk in future discovery.
    """

    @classmethod
    def process_rejection(
        cls,
        lead_id: str,
        reason: Optional[str] = None,
        db_conn: Any = None,
        redis_conn: Any = None,
        knowledge_model: Any = None
    ) -> Dict[str, Any]:
        """
        Executes full rejection lifecycle: DB updates, campaign cancellation,
        feature extraction, and negative pattern registration.
        """
        if not db_conn:
            logger.warning("[REJECTION_LEARNER] Cannot process rejection: db_conn is None.")
            return {"success": False, "error": "Database connection unavailable"}

        feedback_reason = reason.strip() if reason and reason.strip() else "User rejected via 24h review"
        learned_negative_tokens: List[str] = []
        learned_negative_phrases: List[str] = []

        try:
            with db_conn.cursor() as cur:
                # 1. Fetch channel details
                cur.execute("""
                    SELECT id, channel_username, description, metadata, lead_score, tier, status
                    FROM leads
                    WHERE id = %s;
                """, (lead_id,))
                lead_row = cur.fetchone()
                if not lead_row:
                    return {"success": False, "error": f"Lead {lead_id} not found"}

                if isinstance(lead_row, dict):
                    ch_user = lead_row["channel_username"]
                    desc = lead_row.get("description") or ""
                    meta = lead_row.get("metadata") or {}
                else:
                    ch_user = lead_row[1]
                    desc = lead_row[2] or ""
                    meta = lead_row[3] or {}

                title = meta.get("title") or ch_user if isinstance(meta, dict) else ch_user

                # Fetch sample recent posts for this channel if available
                cur.execute("""
                    SELECT message_text
                    FROM channel_posts
                    WHERE channel_username = %s
                    ORDER BY id DESC
                    LIMIT 20;
                """, (ch_user,))
                post_rows = cur.fetchall()
                posts = []
                for p in post_rows:
                    text_val = p.get("message_text") if isinstance(p, dict) else p[0]
                    if text_val and len(text_val.strip()) > 5:
                        posts.append(text_val.strip())

                # 2. Update Lead status to 'rejected'
                cur.execute("""
                    UPDATE leads
                    SET status = 'rejected',
                        outreach_priority_reason = %s,
                        lead_score = LEAST(COALESCE(lead_score, 0), 10)
                    WHERE id = %s;
                """, (f"User Rejected: {feedback_reason}", lead_id))

                # 3. Cancel any campaign logs for this lead (Safety: ZERO outreach)
                cur.execute("""
                    UPDATE campaign_logs
                    SET status = 'cancelled'
                    WHERE lead_id = %s AND status IN ('pending', 'pending_review', 'approved');
                """, (lead_id,))
                cancelled_outreach_count = cur.rowcount

                # 4. Upsert into corpus_channels as 'negative_spam'
                corpus_doc = {
                    "channel_id": str(lead_id),
                    "channel_username": ch_user,
                    "title": title,
                    "corpus_type": "negative_spam",
                    "is_admin": False,
                    "is_creator": False,
                    "member_count": 0,
                    "about": desc,
                    "sample_posts": json.dumps(posts),
                    "sample_posts_count": len(posts)
                }

                cur.execute("""
                    INSERT INTO corpus_channels (
                        channel_id, channel_username, title, corpus_type,
                        is_admin, is_creator, member_count, about, sample_posts,
                        sample_posts_count, last_harvested_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, NOW(), NOW())
                    ON CONFLICT (channel_username)
                    DO UPDATE SET
                        corpus_type = 'negative_spam',
                        about = EXCLUDED.about,
                        sample_posts = EXCLUDED.sample_posts,
                        sample_posts_count = EXCLUDED.sample_posts_count,
                        last_harvested_at = NOW(),
                        updated_at = NOW();
                """, (
                    corpus_doc["channel_id"],
                    corpus_doc["channel_username"],
                    corpus_doc["title"],
                    corpus_doc["corpus_type"],
                    corpus_doc["is_admin"],
                    corpus_doc["is_creator"],
                    corpus_doc["member_count"],
                    corpus_doc["about"],
                    corpus_doc["sample_posts"],
                    corpus_doc["sample_posts_count"]
                ))

                # 5. Extract features via PatternMiner
                features = PatternMiner.extract_channel_features({
                    "title": title,
                    "about": desc,
                    "posts": posts
                })

                keywords = list(features.get("keyword", set()))[:15]
                phrases = list(features.get("phrase", set()))[:10]

                # 6. Register / Penalize in discovered_signals table
                for kw in keywords:
                    norm_kw = PatternMiner.normalize_arabic(kw)
                    if len(norm_kw) < 3:
                        continue
                    cur.execute("""
                        INSERT INTO discovered_signals (
                            signal_type, signal_value, normalized_value, category,
                            status, confidence_score, contrast_score, positive_support_count,
                            negative_penalty_count, discovery_count, created_at, updated_at
                        ) VALUES (%s, %s, %s, 'negative_spam', 'active', 0.1, -2.5, 0, 1, 1, NOW(), NOW())
                        ON CONFLICT (signal_type, signal_value)
                        DO UPDATE SET
                            negative_penalty_count = discovered_signals.negative_penalty_count + 1,
                            contrast_score = discovered_signals.contrast_score - 1.0,
                            confidence_score = GREATEST(0.0, discovered_signals.confidence_score - 0.15),
                            updated_at = NOW();
                    """, (SignalType.KEYWORD, kw, norm_kw))
                    learned_negative_tokens.append(kw)

                for ph in phrases:
                    norm_ph = PatternMiner.normalize_arabic(ph)
                    if len(norm_ph) < 5:
                        continue
                    cur.execute("""
                        INSERT INTO discovered_signals (
                            signal_type, signal_value, normalized_value, category,
                            status, confidence_score, contrast_score, positive_support_count,
                            negative_penalty_count, discovery_count, created_at, updated_at
                        ) VALUES (%s, %s, %s, 'negative_spam', 'active', 0.1, -3.0, 0, 1, 1, NOW(), NOW())
                        ON CONFLICT (signal_type, signal_value)
                        DO UPDATE SET
                            negative_penalty_count = discovered_signals.negative_penalty_count + 1,
                            contrast_score = discovered_signals.contrast_score - 1.5,
                            confidence_score = GREATEST(0.0, discovered_signals.confidence_score - 0.2),
                            updated_at = NOW();
                    """, (SignalType.PHRASE, ph, norm_ph))
                    learned_negative_phrases.append(ph)

                db_conn.commit()

            # 7. Update Redis negative sets for real-time worker synchronization
            if redis_conn:
                try:
                    if learned_negative_tokens:
                        redis_conn.sadd(REDIS_NEG_KEYWORDS_KEY, *[t.lower() for t in learned_negative_tokens])
                    if learned_negative_phrases:
                        redis_conn.sadd(REDIS_NEG_PHRASES_KEY, *[p.lower() for p in learned_negative_phrases])
                    logger.info(f"[REJECTION_LEARNER] Synced {len(learned_negative_tokens)} neg keywords and {len(learned_negative_phrases)} neg phrases to Redis.")
                except Exception as r_err:
                    logger.warning(f"[REJECTION_LEARNER] Redis sync notice: {r_err}")

            # 8. Update in-memory KnowledgeModel if present
            if knowledge_model and hasattr(knowledge_model, 'load_from_db'):
                try:
                    knowledge_model.load_from_db(db_conn)
                except Exception as km_err:
                    logger.debug(f"[REJECTION_LEARNER] KnowledgeModel refresh notice: {km_err}")

            logger.info(
                f"[REJECTION_LEARNER] Successfully learned from rejection of @{ch_user}. "
                f"Cancelled outreach: {cancelled_outreach_count}. "
                f"Negative tokens: {len(learned_negative_tokens)}, Negative phrases: {len(learned_negative_phrases)}."
            )

            return {
                "success": True,
                "lead_id": lead_id,
                "channel_username": ch_user,
                "status": "rejected",
                "cancelled_outreach_count": cancelled_outreach_count,
                "learned_negative_tokens": learned_negative_tokens[:8],
                "learned_negative_phrases": learned_negative_phrases[:5]
            }

        except Exception as e:
            logger.error(f"[REJECTION_LEARNER] Error during rejection learning: {e}", exc_info=True)
            try:
                db_conn.rollback()
            except Exception:
                pass
            return {"success": False, "error": str(e)}
