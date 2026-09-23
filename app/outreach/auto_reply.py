"""
app/outreach/auto_reply.py — Real-time and Fallback Auto-Reply Dispatcher Engine
"""

import os
import json
import random
import logging
import asyncio
from typing import Optional, Callable, List
from psycopg2.extras import RealDictCursor
from telethon import events, errors
from app.outreach.emergency import is_kill_switch_active, is_outreach_enabled, emergency_stop
from app.outreach.dry_run import is_dry_run


class AutoReplyEngine:
    """
    Manages automated second-message outreach delivery when leads reply to initial campaigns.
    Supports real-time Telegram event listening and scheduled safety fallback checks.
    """

    def __init__(
        self,
        user_client,
        redis_conn,
        db_helper=None,
        shutdown_event: Optional[asyncio.Event] = None,
        resolve_media_fn: Optional[Callable[[Optional[str]], List[str]]] = None,
        db_conn=None
    ):
        self.user_client = user_client
        self.redis_conn = redis_conn
        self.db_helper = db_helper
        self.db_conn = db_conn or (db_helper.conn if db_helper and hasattr(db_helper, 'conn') else None)
        self.shutdown_event = shutdown_event or asyncio.Event()
        self._resolve_media = resolve_media_fn or self._default_resolve_media
        self._registered_handler = None

    @property
    def is_handler_registered(self) -> bool:
        return self._registered_handler is not None

    @staticmethod
    def _default_resolve_media(media_path: Optional[str]) -> List[str]:
        if not media_path:
            return []
        if media_path.startswith('[') and media_path.endswith(']'):
            try:
                paths = json.loads(media_path)
                return [p for p in paths if os.path.exists(p)]
            except Exception:
                pass
        elif ',' in media_path:
            return [f.strip() for f in media_path.split(',') if f.strip() and os.path.exists(f.strip())]
        elif os.path.exists(media_path):
            return [media_path]
        return []

    def register_handler(self):
        """
        Registers real-time Telegram event listener on user_client.
        Listens for incoming private messages from outreach campaign leads.
        """
        if not self.user_client:
            return

        client = self.user_client

        @client.on(events.NewMessage(incoming=True))
        async def handle_incoming_user_message(event):
            try:
                if not event.is_private or getattr(event, 'out', False):
                    return

                sender_id = event.sender_id
                if not sender_id:
                    return

                # Exclude self messages
                try:
                    me = await client.get_me()
                    if me and sender_id == me.id:
                        return
                except Exception:
                    pass

                sender = await event.get_sender()
                if not sender or getattr(sender, 'bot', False):
                    return

                raw_username = (getattr(sender, 'username', None) or '').strip().lstrip('@')

                # Distributed lock to serialize concurrent message events from the same sender
                lock_key = f"autoreply_lock:user:{sender_id}"
                if not self.redis_conn.set(lock_key, "1", nx=True, ex=60):
                    return

                done_key = f"autoreply_done:{sender_id}"
                if self.redis_conn.get(done_key):
                    return
                if raw_username and self.redis_conn.get(f"autoreply_done:{raw_username.lower()}"):
                    return

                # Query database for matching campaign lead
                self.db_helper.check_connection()
                conn = self.db_helper.conn
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT cl.id as log_id, cl.campaign_id, cl.lead_id, cl.auto_reply_sent, cl.user_replied,
                               c.auto_reply_enabled, c.auto_reply_message_text, c.auto_reply_media_path,
                               l.contact_username, l.channel_username
                        FROM campaign_logs cl
                        JOIN campaigns c ON cl.campaign_id = c.id
                        JOIN leads l ON cl.lead_id = l.id
                        WHERE cl.status = 'sent'
                          AND (
                              (cl.telegram_user_id IS NOT NULL AND cl.telegram_user_id = %s)
                              OR (%s != '' AND LOWER(l.contact_username) = LOWER(%s))
                          )
                        ORDER BY cl.sent_at DESC
                        LIMIT 1;
                    """, (sender_id, raw_username, raw_username))
                    matched_lead = cur.fetchone()

                    if not matched_lead:
                        return

                    log_id = matched_lead['log_id']
                    auto_reply_already_sent = matched_lead.get('auto_reply_sent', False)
                    auto_reply_enabled = matched_lead.get('auto_reply_enabled', True)
                    auto_reply_text = matched_lead.get('auto_reply_message_text')
                    auto_reply_media = matched_lead.get('auto_reply_media_path')

                    # Lock log_id specifically to serialize with fallback or parallel tasks
                    log_lock_key = f"autoreply_lock:log:{log_id}"
                    if not self.redis_conn.set(log_lock_key, "1", nx=True, ex=120):
                        logging.info(f"Auto-Reply Engine: Log {log_id} already locked by another task. Skipping.")
                        return

                    if self.redis_conn.get(f"autoreply_done:{log_id}"):
                        return
                    if self.redis_conn.get(f"autoreply_dispatched:{log_id}"):
                        return

                    # Record user_replied = TRUE with user_replied_at timestamp
                    cur.execute("""
                        UPDATE campaign_logs 
                        SET user_replied = TRUE, 
                            user_replied_at = COALESCE(user_replied_at, NOW()),
                            telegram_user_id = COALESCE(telegram_user_id, %s) 
                        WHERE id = %s;
                    """, (sender_id, log_id))
                    conn.commit()

                    # Mark in-flight in Redis with 120s TTL
                    self.redis_conn.set(f"autoreply_in_flight:{log_id}", "1", ex=120)

                    logging.info(f"Auto-Reply Engine: Detected reply from lead @{raw_username} (ID: {sender_id}, log: {log_id})!")

                    if auto_reply_already_sent:
                        self.redis_conn.set(done_key, "1", ex=86400 * 30)
                        self.redis_conn.set(f"autoreply_done:{log_id}", "1", ex=86400 * 30)
                        self.redis_conn.delete(f"autoreply_in_flight:{log_id}")
                        return

                    if not auto_reply_enabled or not auto_reply_text:
                        logging.info("Auto-Reply Engine: Auto-reply disabled or text unset. user_replied recorded.")
                        self.redis_conn.delete(f"autoreply_in_flight:{log_id}")
                        return

                    # ── Multi-Tier Safety Guard Check ────────────────────────
                    is_killed, kill_reason = is_kill_switch_active(self.redis_conn)
                    if is_killed or not is_outreach_enabled(self.redis_conn) or is_dry_run(self.redis_conn):
                        logging.info(f"Auto-Reply Engine: Outbound dispatch blocked by safety gate (kill_switch={is_killed}, reason={kill_reason}). Skipping 2nd message.")
                        self.redis_conn.delete(f"autoreply_in_flight:{log_id}")
                        return

                    # Human-like delay
                    delay_sec = random.randint(6, 15)
                    logging.info(f"Auto-Reply Engine: Waiting {delay_sec}s human delay before replying to @{raw_username}...")
                    await asyncio.sleep(delay_sec)

                    # Simulated typing action
                    try:
                        async with client.action(event.chat_id, 'typing'):
                            await asyncio.sleep(random.randint(2, 4))
                    except Exception:
                        pass

                    # ── Post-Sleep Re-Verification (Critical Duplicate Prevention) ──
                    if self.redis_conn.get(f"autoreply_dispatched:{log_id}"):
                        logging.info(f"Auto-Reply Engine: Log {log_id} already marked dispatched during delay. Skipping duplicate send.")
                        self.redis_conn.delete(f"autoreply_in_flight:{log_id}")
                        return

                    if self.redis_conn.get(f"autoreply_done:{log_id}") or self.redis_conn.get(done_key):
                        logging.info(f"Auto-Reply Engine: Log {log_id} or user {sender_id} marked done during delay. Skipping duplicate send.")
                        self.redis_conn.delete(f"autoreply_in_flight:{log_id}")
                        return

                    # Re-query DB in case fallback sent it during the delay
                    self.db_helper.check_connection()
                    conn = self.db_helper.conn
                    with conn.cursor(cursor_factory=RealDictCursor) as check_cur:
                        check_cur.execute("SELECT auto_reply_sent FROM campaign_logs WHERE id = %s;", (log_id,))
                        status_row = check_cur.fetchone()
                        if status_row and status_row.get('auto_reply_sent'):
                            logging.info(f"Auto-Reply Engine: DB confirms log {log_id} already has auto_reply_sent=TRUE. Skipping duplicate send.")
                            self.redis_conn.set(done_key, "1", ex=86400 * 30)
                            self.redis_conn.set(f"autoreply_done:{log_id}", "1", ex=86400 * 30)
                            self.redis_conn.delete(f"autoreply_in_flight:{log_id}")
                            return

                    # ── Atomic Single-Winner Dispatch Token ──
                    if not self.redis_conn.set(f"autoreply_dispatched:{log_id}", "1", nx=True, ex=86400 * 30):
                        logging.info(f"Auto-Reply Engine: Atomic dispatch token already acquired for log {log_id}. Skipping.")
                        self.redis_conn.delete(f"autoreply_in_flight:{log_id}")
                        return

                    # Send second message
                    media_files = self._resolve_media(auto_reply_media)
                    if media_files:
                        if len(media_files) == 1:
                            await client.send_message(event.chat_id, auto_reply_text, file=media_files[0])
                        else:
                            await client.send_file(event.chat_id, media_files, caption=auto_reply_text)
                    else:
                        await client.send_message(event.chat_id, auto_reply_text)

                    with conn.cursor() as upd_cur:
                        upd_cur.execute("""
                            UPDATE campaign_logs 
                            SET auto_reply_sent = TRUE, 
                                auto_reply_sent_at = NOW(), 
                                auto_reply_error = NULL 
                            WHERE id = %s;
                        """, (log_id,))
                        conn.commit()

                    self.redis_conn.delete(f"autoreply_in_flight:{log_id}")
                    self.redis_conn.set(done_key, "1", ex=86400 * 30)
                    self.redis_conn.set(f"autoreply_done:{log_id}", "1", ex=86400 * 30)
                    if raw_username:
                        self.redis_conn.set(f"autoreply_done:{raw_username.lower()}", "1", ex=86400 * 30)

                    logging.info(f"Auto-Reply Engine: Successfully sent 2nd message to @{raw_username} (ID: {sender_id}, log: {log_id})!")

            except errors.FloodWaitError as fw:
                logging.error(f"🚨 Auto-Reply FloodWait: {fw.seconds}s. TRIPPING EMERGENCY STOP TO PROTECT ACCOUNT!")
                emergency_stop(self.redis_conn)
                await asyncio.sleep(fw.seconds)
            except errors.PeerFloodError as pf:
                logging.error(f"🚨🚨 Auto-Reply PeerFloodError: {pf}. TRIPPING EMERGENCY STOP TO PROTECT ACCOUNT!")
                emergency_stop(self.redis_conn)
            except Exception as e:
                logging.error(f"Auto-Reply Engine error: {e}", exc_info=True)
                try:
                    conn.rollback()
                except Exception:
                    pass

        self._registered_handler = handle_incoming_user_message
        logging.info("Auto-Reply real-time event listener registered on User Client.")

    def unregister_handlers(self):
        """Safely detaches the event handler from user_client if active."""
        if self.user_client and self._registered_handler:
            try:
                self.user_client.remove_event_handler(self._registered_handler)
                self._registered_handler = None
                logging.info("Auto-Reply real-time event listener detached.")
            except Exception as e:
                logging.debug(f"Error detaching auto-reply handler: {e}")

    async def fallback_loop(self):
        """
        Safety fallback dispatcher (runs every 30 seconds):
        Queries DB for leads where user_replied = TRUE but auto_reply_sent = FALSE,
        respecting a 2-minute grace period to prevent race conditions with real-time events.
        """
        logging.info("Auto-Reply fallback dispatcher task started.")
        while not self.shutdown_event.is_set():
            try:
                await asyncio.sleep(30)
                if not self.user_client or not self.user_client.is_connected():
                    continue

                # Multi-Tier Safety Guard Check
                is_killed, kill_reason = is_kill_switch_active(self.redis_conn)
                if is_killed or not is_outreach_enabled(self.redis_conn) or is_dry_run(self.redis_conn):
                    continue

                self.db_helper.check_connection()
                conn = self.db_helper.conn
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT id, auto_reply_enabled, auto_reply_message_text, auto_reply_media_path
                        FROM campaigns WHERE status = 'active' LIMIT 1;
                    """)
                    camp = cur.fetchone()
                    if not camp or not camp.get('auto_reply_enabled') or not camp.get('auto_reply_message_text'):
                        continue

                    auto_text = camp['auto_reply_message_text']
                    auto_media = camp['auto_reply_media_path']

                    cur.execute("""
                        SELECT cl.id as log_id, cl.telegram_user_id, l.contact_username
                        FROM campaign_logs cl
                        JOIN leads l ON cl.lead_id = l.id
                        WHERE cl.status = 'sent'
                          AND cl.user_replied = TRUE
                          AND cl.auto_reply_sent = FALSE
                          AND (cl.user_replied_at IS NULL OR cl.user_replied_at < NOW() - INTERVAL '2 minutes')
                          AND cl.sent_at >= NOW() - INTERVAL '30 days'
                        ORDER BY cl.sent_at ASC
                        LIMIT 5;
                    """)
                    unreplied_leads = cur.fetchall()

                    for row in unreplied_leads:
                        log_id = row['log_id']
                        contact_username = row.get('contact_username')
                        telegram_user_id = row.get('telegram_user_id')

                        if not contact_username and not telegram_user_id:
                            continue

                        # Check in-flight or already dispatched guards
                        if self.redis_conn.get(f"autoreply_in_flight:{log_id}"):
                            logging.info(f"Auto-Reply Fallback: Log {log_id} currently in-flight in real-time handler. Skipping.")
                            continue

                        if self.redis_conn.get(f"autoreply_dispatched:{log_id}"):
                            continue

                        if self.redis_conn.get(f"autoreply_done:{log_id}"):
                            continue

                        if telegram_user_id and self.redis_conn.get(f"autoreply_done:{telegram_user_id}"):
                            continue

                        clean_username = contact_username.strip().lower().lstrip('@') if contact_username else None
                        if clean_username and self.redis_conn.get(f"autoreply_done:{clean_username}"):
                            continue

                        # Distributed locks
                        lock_key = f"autoreply_lock:log:{log_id}"
                        if not self.redis_conn.set(lock_key, "1", nx=True, ex=120):
                            continue

                        if telegram_user_id:
                            self.redis_conn.set(f"autoreply_lock:user:{telegram_user_id}", "1", nx=True, ex=120)

                        try:
                            # Re-verify DB before network calls
                            cur.execute("SELECT auto_reply_sent FROM campaign_logs WHERE id = %s;", (log_id,))
                            v_row = cur.fetchone()
                            if v_row and v_row.get('auto_reply_sent'):
                                self.redis_conn.set(f"autoreply_done:{log_id}", "1", ex=86400 * 30)
                                continue

                            peer = None
                            if clean_username:
                                try:
                                    peer = await self.user_client.get_input_entity(clean_username)
                                except Exception as u_err:
                                    logging.debug(f"Auto-Reply Fallback: Resolve by username @{contact_username} failed: {u_err}")

                            if not peer and telegram_user_id:
                                try:
                                    peer = await self.user_client.get_input_entity(int(telegram_user_id))
                                except Exception as id_err:
                                    logging.debug(f"Auto-Reply Fallback: Resolve by user_id {telegram_user_id} failed: {id_err}")

                            if not peer:
                                logging.warning(f"Auto-Reply Fallback: Could not resolve peer for log {log_id} (@{contact_username}, ID:{telegram_user_id})")
                                continue

                            # Atomic Single-Winner Dispatch Token
                            if not self.redis_conn.set(f"autoreply_dispatched:{log_id}", "1", nx=True, ex=86400 * 30):
                                logging.info(f"Auto-Reply Fallback: Dispatch token already acquired for log {log_id}. Skipping.")
                                continue

                            logging.info(f"Auto-Reply Fallback: Sending 2nd message (with media) to @{contact_username} / {telegram_user_id} (log {log_id})...")
                            media_files = self._resolve_media(auto_media)
                            if media_files:
                                if len(media_files) == 1:
                                    await self.user_client.send_message(peer, auto_text, file=media_files[0])
                                else:
                                    await self.user_client.send_file(peer, media_files, caption=auto_text)
                            else:
                                await self.user_client.send_message(peer, auto_text)

                            cur.execute("""
                                UPDATE campaign_logs
                                SET auto_reply_sent = TRUE, auto_reply_sent_at = NOW(), auto_reply_error = NULL
                                WHERE id = %s;
                            """, (log_id,))
                            conn.commit()

                            self.redis_conn.set(f"autoreply_done:{log_id}", "1", ex=86400 * 30)
                            if clean_username:
                                self.redis_conn.set(f"autoreply_done:{clean_username}", "1", ex=86400 * 30)
                            if telegram_user_id:
                                self.redis_conn.set(f"autoreply_done:{telegram_user_id}", "1", ex=86400 * 30)
                            self.redis_conn.delete(f"autoreply_in_flight:{log_id}")

                            logging.info(f"Auto-Reply Fallback: Successfully sent 2nd message to @{contact_username} / {telegram_user_id}!")
                            await asyncio.sleep(random.randint(5, 10))

                        except errors.FloodWaitError as fw:
                            logging.warning(f"Auto-Reply Fallback FloodWait: {fw.seconds}s.")
                            await asyncio.sleep(fw.seconds)
                            break
                        except Exception as send_err:
                            logging.error(f"Auto-Reply Fallback error sending to @{contact_username} / {telegram_user_id}: {send_err}")
                            cur.execute("UPDATE campaign_logs SET auto_reply_error = %s WHERE id = %s", (str(send_err), log_id))
                            conn.commit()

            except Exception as fb_err:
                logging.debug(f"Auto-reply fallback note: {fb_err}")
