"""
app/learning/corpus_harvester.py — Ground Truth Corpus Harvester

Discovers and harvests Tamer's Admin Channels (Gold Positive Corpus) and
Rejected Leads (Negative Corpus). Populates corpus_channels and drives
pattern mining.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from app.core.membership_governor import MembershipGovernor
from app.learning.pattern_miner import PatternMiner
from app.learning.signal_lifecycle import SignalLifecycle, SignalStatus

logger = logging.getLogger(__name__)


class CorpusHarvester:
    """
    Harvests Gold Positive and Negative channel data for adaptive learning.
    """

    @classmethod
    async def harvest_gold_corpus(
        cls,
        client,
        db_conn,
        max_channels: int = 60,
        max_posts_per_channel: int = 40
    ) -> List[Dict[str, Any]]:
        """
        Scans Tamer's account for Admin/Creator channels, fetches title, about,
        and recent post samples, and upserts them into corpus_channels.
        """
        if not client:
            logger.warning("[HARVESTER] TelegramClient not provided for harvest_gold_corpus.")
            return []

        logger.info("[HARVESTER] Scanning Tamer's dialogs for Admin/Creator channels...")
        gold_channels = []

        try:
            # Telethon dialog scanning
            dialogs = await client.get_dialogs(limit=None)
            admin_entities = []

            for d in dialogs:
                if not d.is_channel and not d.is_group:
                    continue
                if MembershipGovernor.is_admin_or_creator(d.entity):
                    admin_entities.append(d.entity)

            logger.info(f"[HARVESTER] Found {len(admin_entities)} Admin/Creator channels.")

            from telethon.tl.functions.channels import GetFullChannelRequest

            for entity in admin_entities[:max_channels]:
                ch_id = str(getattr(entity, 'id', ''))
                username = getattr(entity, 'username', None)
                if not username:
                    username = f"admin_{ch_id}"
                title = getattr(entity, 'title', '') or ''
                is_admin = bool(getattr(entity, 'admin_rights', None))
                is_creator = bool(getattr(entity, 'creator', False))
                member_count = getattr(entity, 'participants_count', 0) or 0

                about = ""
                try:
                    full = await client(GetFullChannelRequest(entity))
                    about = getattr(full.full_chat, 'about', '') or ''
                except Exception as e:
                    logger.debug(f"[HARVESTER] Could not fetch full about for {username}: {e}")

                # Fetch sample recent text posts
                sample_posts = []
                try:
                    async for msg in client.iter_messages(entity, limit=max_posts_per_channel):
                        if msg and msg.text and len(msg.text.strip()) > 10:
                            sample_posts.append(msg.text.strip())
                except Exception as e:
                    logger.debug(f"[HARVESTER] Could not fetch messages for {username}: {e}")

                ch_data = {
                    "channel_id": ch_id,
                    "channel_username": username,
                    "title": title,
                    "corpus_type": "gold_admin",
                    "is_admin": is_admin,
                    "is_creator": is_creator,
                    "member_count": member_count,
                    "about": about,
                    "posts": sample_posts,
                    "sample_posts_count": len(sample_posts)
                }
                gold_channels.append(ch_data)

                # Persist to DB if connected
                if db_conn:
                    cls._upsert_corpus_channel(db_conn, ch_data)

            logger.info(f"[HARVESTER] Successfully harvested {len(gold_channels)} Gold channels.")
        except Exception as e:
            logger.error(f"[HARVESTER] Error during harvest_gold_corpus: {e}", exc_info=True)

        return gold_channels

    @classmethod
    def harvest_negative_corpus(cls, db_conn, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Samples rejected channels from `leads` table as negative spam examples.
        """
        if not db_conn:
            logger.warning("[HARVESTER] Database connection not provided for negative corpus.")
            return []

        negative_channels = []
        query = """
        SELECT 
            l.id::text AS channel_id,
            l.channel_username,
            COALESCE(l.metadata->>'title', l.channel_username) AS title,
            COALESCE(l.description, '') AS description,
            COALESCE(l.outreach_priority_reason, l.classification, '') AS reason
        FROM leads l
        WHERE l.status = 'rejected'
          AND (l.forex_intent_score = 0 OR l.forex_intent_score IS NULL)
          AND (l.commercial_intent_score = 0 OR l.commercial_intent_score IS NULL)
          AND l.channel_username NOT IN (
              SELECT channel_username FROM corpus_channels WHERE corpus_type = 'gold_admin'
          )
          AND (l.description IS NOT NULL AND length(l.description) > 15)
          AND l.description NOT LIKE '%does not exist%'
          AND l.description NOT LIKE '%Blacklisted entity%'
          AND l.description NOT LIKE '%Error during validation%'
          AND l.description NOT LIKE '%Inactive non-forex channel%'
          AND lower(l.description) NOT LIKE '%xauusd%'
          AND lower(l.description) NOT LIKE '%forex%'
          AND lower(l.description) NOT LIKE '%trading%'
          AND lower(l.description) NOT LIKE '%trader%'
          AND lower(l.description) NOT LIKE '%crypto%'
          AND lower(l.description) NOT LIKE '%gold%'
          AND lower(l.description) NOT LIKE '%signal%'
          AND lower(l.description) NOT LIKE '%تداول%'
          AND lower(l.description) NOT LIKE '%فوركس%'
          AND lower(l.description) NOT LIKE '%تريدر%'
          AND lower(l.description) NOT LIKE '%ذهب%'
          AND lower(l.description) NOT LIKE '%عملات%'
          AND lower(l.description) NOT LIKE '%تحليل%'
          AND lower(l.description) NOT LIKE '%صفقات%'
          AND lower(l.description) NOT LIKE '%توصيات%'
          AND lower(l.description) NOT LIKE '%بيتكوين%'
          AND lower(l.description) NOT LIKE '%إشارات%'
          AND lower(l.description) NOT LIKE '%vip%'
        ORDER BY l.id DESC
        LIMIT %s;
        """
        try:
            with db_conn.cursor() as cur:
                cur.execute(query, (limit,))
                rows = cur.fetchall()
                for r in rows:
                    if isinstance(r, dict):
                        ch_id = str(r.get("channel_id") or "")
                        username = r.get("channel_username") or f"neg_{ch_id}"
                        title = r.get("title") or ""
                        desc = r.get("description") or ""
                        reason = r.get("reason") or ""
                    else:
                        ch_id = str(r[0] or "")
                        username = r[1] or f"neg_{ch_id}"
                        title = r[2] or ""
                        desc = r[3] or ""
                        reason = r[4] or ""

                    ch_data = {
                        "channel_id": ch_id,
                        "channel_username": username,
                        "title": title,
                        "corpus_type": "negative_spam",
                        "is_admin": False,
                        "is_creator": False,
                        "member_count": 0,
                        "about": desc,
                        "posts": [reason] if reason else [],
                        "sample_posts_count": 1 if reason else 0
                    }
                    negative_channels.append(ch_data)
                    cls._upsert_corpus_channel(db_conn, ch_data)

            logger.info(f"[HARVESTER] Harvested {len(negative_channels)} negative spam channels from leads.")
        except Exception as e:
            logger.error(f"[HARVESTER] Error harvesting negative corpus: {e}")

        return negative_channels

    @classmethod
    def load_cached_corpus(cls, db_conn, corpus_type: str = "gold_admin") -> List[Dict[str, Any]]:
        """
        Loads cached corpus channels from PostgreSQL.
        """
        if not db_conn:
            return []

        channels = []
        query = """
        SELECT channel_id, channel_username, title, about, sample_posts
        FROM corpus_channels
        WHERE corpus_type = %s;
        """
        try:
            with db_conn.cursor() as cur:
                cur.execute(query, (corpus_type,))
                for row in cur.fetchall():
                    if isinstance(row, dict):
                        ch_id = row["channel_id"]
                        ch_user = row["channel_username"]
                        ch_title = row.get("title") or ""
                        ch_about = row.get("about") or ""
                        posts = row.get("sample_posts") or []
                    else:
                        ch_id = row[0]
                        ch_user = row[1]
                        ch_title = row[2] or ""
                        ch_about = row[3] or ""
                        posts = row[4] or []

                    if isinstance(posts, str):
                        try:
                            posts = json.loads(posts)
                        except Exception:
                            posts = []
                    channels.append({
                        "channel_id": ch_id,
                        "channel_username": ch_user,
                        "title": ch_title,
                        "about": ch_about,
                        "posts": posts or []
                    })
        except Exception as e:
            logger.error(f"[HARVESTER] Error loading cached {corpus_type} corpus: {e}")

        return channels

    @classmethod
    def _upsert_corpus_channel(cls, db_conn, ch: Dict[str, Any]) -> None:
        """
        Upserts a channel into corpus_channels.
        """
        query = """
        INSERT INTO corpus_channels (
            channel_id, channel_username, title, corpus_type,
            is_admin, is_creator, member_count, about,
            sample_posts, sample_posts_count, last_harvested_at, updated_at
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s::jsonb, %s, NOW(), NOW()
        )
        ON CONFLICT (channel_username) DO UPDATE SET
            title = EXCLUDED.title,
            corpus_type = EXCLUDED.corpus_type,
            is_admin = EXCLUDED.is_admin,
            is_creator = EXCLUDED.is_creator,
            member_count = EXCLUDED.member_count,
            about = EXCLUDED.about,
            sample_posts = EXCLUDED.sample_posts,
            sample_posts_count = EXCLUDED.sample_posts_count,
            last_harvested_at = NOW(),
            updated_at = NOW();
        """
        try:
            with db_conn.cursor() as cur:
                cur.execute(query, (
                    ch.get("channel_id"),
                    ch.get("channel_username"),
                    ch.get("title"),
                    ch.get("corpus_type", "gold_admin"),
                    ch.get("is_admin", False),
                    ch.get("is_creator", False),
                    ch.get("member_count", 0),
                    ch.get("about", ""),
                    json.dumps(ch.get("posts", [])),
                    len(ch.get("posts", [])),
                ))
                db_conn.commit()
        except Exception as e:
            logger.error(f"[HARVESTER] Error upserting corpus channel {ch.get('channel_username')}: {e}")
            try:
                db_conn.rollback()
            except Exception:
                pass

    @classmethod
    async def run_learning_cycle(
        cls,
        client,
        db_conn,
        harvest_fresh: bool = True
    ) -> Dict[str, Any]:
        """
        Full orchestration of the self-learning cycle:
        1. Harvest or load Gold positive channels.
        2. Harvest or load negative channels.
        3. Mine patterns using PatternMiner.
        4. Manage lifecycle and upsert into discovered_signals.
        """
        pos_corpus = []
        neg_corpus = []

        if harvest_fresh and client:
            pos_corpus = await cls.harvest_gold_corpus(client, db_conn)
            if db_conn:
                neg_corpus = cls.harvest_negative_corpus(db_conn)
        else:
            if db_conn:
                pos_corpus = cls.load_cached_corpus(db_conn, "gold_admin")
                neg_corpus = cls.load_cached_corpus(db_conn, "negative_spam")

        if not pos_corpus:
            logger.warning("[HARVESTER] No positive corpus available. Skipping learning cycle.")
            return {"status": "skipped", "reason": "empty_positive_corpus"}

        mined_signals = PatternMiner.mine_and_score(pos_corpus, neg_corpus)
        upserted_count = 0
        active_count = 0

        for sig in mined_signals:
            res = SignalLifecycle.upsert_signal(
                db_conn=db_conn,
                signal_type=sig["signal_type"],
                signal_value=sig["signal_value"],
                normalized_value=sig["normalized_value"],
                category=sig["category"],
                pos_support=sig["positive_support_count"],
                neg_penalty=sig["negative_penalty_count"],
                contrast_score=sig["contrast_score"],
                provenance=sig["provenance_sources"],
                evidence=sig["evidence_samples"]
            )
            if res:
                upserted_count += 1
                if res.get("status") == SignalStatus.ACTIVE:
                    active_count += 1

        summary = {
            "status": "success",
            "gold_channels": len(pos_corpus),
            "negative_channels": len(neg_corpus),
            "signals_mined": len(mined_signals),
            "signals_persisted": upserted_count,
            "active_signals": active_count,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        logger.info(f"[HARVESTER] Learning cycle complete: {summary}")
        return summary
