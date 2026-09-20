"""
app/core/membership_governor.py — Multi-Account Slot Capacity Governor & Membership Lifecycle Manager
"""

import os
import random
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

from telethon import TelegramClient, errors
from telethon.tl.functions.channels import LeaveChannelRequest

logger = logging.getLogger(__name__)


class MembershipGovernor:
    """
    Centralized governor managing the Telegram 500 channel/group limit
    across all active Telegram accounts in the pool.
    
    Guarantees:
    1. 100% IMMUNITY for Admin and Creator channels across all accounts.
    2. Value-driven retention: Retains memberships until discovery value is complete.
    3. Proactive capacity management: Targets < 400 channels (100 free slots buffer).
    4. Anti-Flood pacing: 15-25s delay between leaves, max 30 leaves/day/session.
    """

    TARGET_CHANNEL_LIMIT = 400   # Proactive budget (Telegram limit is 500)
    MAX_LEAVES_PER_DAY = 30      # Strict daily cap per session
    MAX_LEAVES_PER_CYCLE = 15    # Max per 30-min run
    STALE_DAYS_THRESHOLD = 14    # Default TTL for completed research memberships

    def __init__(self, db_conn=None, redis_conn=None):
        self.db = db_conn
        self.redis = redis_conn

    def _get_leaves_today(self, session_name: str) -> int:
        if not self.redis:
            return 0
        try:
            val = self.redis.get(f"hygiene:leaves_today:{session_name}")
            return int(val) if val else 0
        except Exception:
            return 0

    def _increment_leaves_today(self, session_name: str) -> int:
        if not self.redis:
            return 0
        try:
            key = f"hygiene:leaves_today:{session_name}"
            pipe = self.redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, 86400)  # 24 hour TTL
            res = pipe.execute()
            return res[0]
        except Exception:
            return 0

    @staticmethod
    def is_admin_or_creator(dialog_entity) -> bool:
        """
        Determines whether the account has ownership or admin rights in this entity.
        Returns True if account is Creator or has AdminRights.
        """
        if getattr(dialog_entity, 'left', False) or getattr(dialog_entity, 'kicked', False):
            return False

        if hasattr(dialog_entity, 'creator') and dialog_entity.creator:
            return True

        if hasattr(dialog_entity, 'admin_rights') and dialog_entity.admin_rights is not None:
            return True

        return False

    async def scan_account_capacity(self, client: TelegramClient) -> Tuple[List[Any], List[Any]]:
        """
        Fetches all dialogs (active + archive), separates channels/groups into:
        (admin_dialogs, non_admin_dialogs).
        """
        dialogs_active = await client.get_dialogs(limit=None)
        dialogs_archived = []
        try:
            dialogs_archived = await client.get_dialogs(limit=None, folder=1)
        except Exception:
            pass

        all_dialogs = dialogs_active + dialogs_archived
        seen_entity_ids = set()
        channels = []
        for d in all_dialogs:
            if d.is_channel or d.is_group:
                ent_id = getattr(d.entity, 'id', None)
                if ent_id is not None:
                    if ent_id in seen_entity_ids:
                        continue
                    seen_entity_ids.add(ent_id)
                channels.append(d)

        admin_dialogs = []
        non_admin_dialogs = []

        for d in channels:
            if self.is_admin_or_creator(d.entity):
                admin_dialogs.append(d)
            else:
                non_admin_dialogs.append(d)

        return admin_dialogs, non_admin_dialogs

    def check_db_lead_status(self, channel_username: Optional[str]) -> Optional[str]:
        """Queries the status of the lead in PostgreSQL."""
        if not self.db or not channel_username:
            return None
        try:
            with self.db.cursor() as cur:
                cur.execute(
                    "SELECT status FROM leads WHERE LOWER(channel_username) = LOWER(%s) LIMIT 1",
                    (channel_username,)
                )
                row = cur.fetchone()
                return row[0] if row else None
        except Exception as err:
            logger.debug(f"[GOVERNOR] DB lead lookup note for @{channel_username}: {err}")
            try:
                self.db.rollback()
            except Exception:
                pass
            return None

    def get_expired_db_memberships(self, session_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Queries channel_memberships for expired TTL or scheduled leave records."""
        if not self.db:
            return []
        try:
            with self.db.cursor() as cur:
                cur.execute("""
                    SELECT id, channel_id, channel_username, account_session, leave_at
                    FROM channel_memberships
                    WHERE account_session = %s
                      AND current_state IN ('ACTIVE', 'SCHEDULED_LEAVE')
                      AND (leave_at <= NOW() OR current_state = 'SCHEDULED_LEAVE')
                    ORDER BY leave_at ASC NULLS FIRST
                    LIMIT %s;
                """, (session_name, limit))
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as err:
            logger.debug(f"[GOVERNOR] DB expired memberships error: {err}")
            try:
                self.db.rollback()
            except Exception:
                pass
            return []

    def mark_membership_left(self, membership_id: int):
        """Updates channel_memberships record to LEFT."""
        if not self.db:
            return
        try:
            with self.db.cursor() as cur:
                cur.execute("UPDATE channel_memberships SET current_state = 'LEFT', updated_at = NOW() WHERE id = %s", (membership_id,))
            self.db.commit()
        except Exception as err:
            logger.debug(f"[GOVERNOR] DB mark_left error: {err}")
            try:
                self.db.rollback()
            except Exception:
                pass

    async def execute_governance_on_account(
        self,
        session_name: str,
        client: TelegramClient,
        shutdown_event: Optional[asyncio.Event] = None
    ) -> Dict[str, Any]:
        """
        Executes capacity monitoring and safe pruning on a single active Telegram session.
        """
        stats = {
            "session_name": session_name,
            "total_channels": 0,
            "admin_channels": 0,
            "non_admin_channels": 0,
            "leaves_executed": 0,
            "status": "OK"
        }

        leaves_today = self._get_leaves_today(session_name)
        if leaves_today >= self.MAX_LEAVES_PER_DAY:
            logger.info(f"[GOVERNOR] Session '{session_name}' hit daily limit ({leaves_today}/{self.MAX_LEAVES_PER_DAY}). Skipping.")
            stats["status"] = "DAILY_LIMIT_REACHED"
            return stats

        # 1. Inspect account dialogs
        try:
            admin_dialogs, non_admin_dialogs = await self.scan_account_capacity(client)
        except Exception as err:
            logger.warning(f"[GOVERNOR] Could not scan dialogs for session '{session_name}': {err}")
            stats["status"] = f"SCAN_ERROR: {err}"
            return stats

        total_joined = len(admin_dialogs) + len(non_admin_dialogs)
        stats["total_channels"] = total_joined
        stats["admin_channels"] = len(admin_dialogs)
        stats["non_admin_channels"] = len(non_admin_dialogs)

        logger.info(
            f"[GOVERNOR] Session '{session_name}': {total_joined} total channels/groups "
            f"({len(admin_dialogs)} Admin/Immune, {len(non_admin_dialogs)} Non-Admin). "
            f"Target: < {self.TARGET_CHANNEL_LIMIT} (Budget headroom: {max(0, 500 - total_joined)} slots)."
        )

        # 2. Build Candidate Eviction List
        candidates = []
        now_utc = datetime.now(timezone.utc)

        for d in non_admin_dialogs:
            if len(candidates) >= self.MAX_LEAVES_PER_CYCLE:
                break

            entity = d.entity
            ch_username = getattr(entity, 'username', None)
            ch_id = getattr(entity, 'id', None)

            # Join age calculation
            dialog_date = getattr(d, 'date', None)
            days_joined = None
            if dialog_date:
                if dialog_date.tzinfo is None:
                    dialog_date = dialog_date.replace(tzinfo=timezone.utc)
                days_joined = (now_utc - dialog_date).days

            # DB lead status check
            db_status = self.check_db_lead_status(ch_username)

            # Decision Logic:
            # A) Value complete: Already fully processed/contacted/rejected in database
            reason = None
            if db_status in ('validated', 'rejected', 'sent', 'skipped', 'failed', 'contacted'):
                reason = f"value_complete_{db_status}"
            # B) Stale membership: Joined > 14 days ago and not a 'new' lead pending validation
            elif days_joined is not None and days_joined >= self.STALE_DAYS_THRESHOLD:
                if db_status != 'new':
                    reason = f"stale_ttl_{days_joined}d"
            # C) Capacity Pressure: If total channels > TARGET_CHANNEL_LIMIT (400)
            elif total_joined > self.TARGET_CHANNEL_LIMIT and db_status is None:
                if days_joined is not None and days_joined >= 7:
                    reason = f"capacity_budget_exceeded_{total_joined}"

            if reason:
                candidates.append({
                    "dialog": d,
                    "entity": entity,
                    "username": ch_username or str(ch_id),
                    "reason": reason,
                    "days": days_joined,
                    "db_status": db_status
                })

        # 3. Check PostgreSQL membership table expired entries
        db_expired = self.get_expired_db_memberships(session_name, limit=10)
        for mem in db_expired:
            mem_user = mem.get("channel_username")
            if mem_user and not any(c["username"].lower() == mem_user.lower() for c in candidates):
                if len(candidates) < self.MAX_LEAVES_PER_CYCLE:
                    candidates.append({
                        "dialog": None,
                        "entity": None,
                        "username": mem_user,
                        "reason": "membership_ttl_expired",
                        "days": None,
                        "db_status": None,
                        "membership_id": mem.get("id")
                    })

        # 4. Execute Safe Leaves
        leaves_done = 0
        for cand in candidates:
            if shutdown_event and shutdown_event.is_set():
                break

            current_leaves = self._get_leaves_today(session_name)
            if current_leaves >= self.MAX_LEAVES_PER_DAY:
                logger.info(f"[GOVERNOR] Daily leave cap reached for '{session_name}'. Halting.")
                break

            target_name = cand["username"]
            target_reason = cand["reason"]

            try:
                if cand["entity"]:
                    # Never leave admin channels
                    if self.is_admin_or_creator(cand["entity"]):
                        continue
                    await client(LeaveChannelRequest(cand["entity"]))
                else:
                    try:
                        resolved_ent = await client.get_entity(target_name)
                        if self.is_admin_or_creator(resolved_ent):
                            continue
                        await client(LeaveChannelRequest(resolved_ent))
                    except Exception:
                        if cand.get("membership_id"):
                            self.mark_membership_left(cand["membership_id"])
                        continue

                leaves_done += 1
                self._increment_leaves_today(session_name)
                if cand.get("membership_id"):
                    self.mark_membership_left(cand["membership_id"])

                logger.info(
                    f"[GOVERNOR] [{session_name}] LEFT @{target_name} "
                    f"(reason={target_reason}, days={cand.get('days', '?')}, db={cand.get('db_status', 'none')})"
                )

                # Human-like safe pacing (15-25 seconds delay)
                delay = 15 + random.uniform(0, 10)
                await asyncio.sleep(delay)

            except errors.FloodWaitError as fwe:
                logger.warning(f"[GOVERNOR] FloodWaitError on '{session_name}' ({fwe.seconds}s). Stopping cycle.")
                break
            except Exception as le_err:
                err_str = str(le_err).lower()
                if "not_participant" in err_str or "user_not_participant" in err_str:
                    if cand.get("membership_id"):
                        self.mark_membership_left(cand["membership_id"])
                else:
                    logger.warning(f"[GOVERNOR] Error leaving @{target_name} on '{session_name}': {le_err}")

        stats["leaves_executed"] = leaves_done
        return stats

    async def run_multi_account_cycle(
        self,
        clients_map: Dict[str, TelegramClient],
        shutdown_event: Optional[asyncio.Event] = None
    ) -> Dict[str, Any]:
        """
        Runs the governance cycle across ALL registered Telegram sessions.
        """
        results = {}
        for session_name, client in clients_map.items():
            if not client:
                continue

            is_conn_fn = getattr(client, 'is_connected', None)
            if callable(is_conn_fn):
                try:
                    conn_val = is_conn_fn()
                    if asyncio.iscoroutine(conn_val):
                        conn_val = await conn_val
                    if not conn_val:
                        continue
                except Exception:
                    pass

            try:
                res = await self.execute_governance_on_account(session_name, client, shutdown_event)
                results[session_name] = res
            except Exception as acc_err:
                logger.error(f"[GOVERNOR] Error governing session '{session_name}': {acc_err}", exc_info=True)

        return results
