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
                lock_key = f"autoreply_lock:{sender_id}"
                if not self.redis_conn.set(lock_key, "1", nx=True, ex=30):
                    return

                done_key = f"autoreply_done:{sender_id}"
                if self.redis_conn.get(done_key):
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

                    # Record user_replied = TRUE
                    cur.execute("""
                        UPDATE campaign_logs 
                        SET user_replied = TRUE, 
                            telegram_user_id = COALESCE(telegram_user_id, %s) 
                        WHERE id = %s;
                    """, (sender_id, log_id))
                    conn.commit()

                    logging.info(f"Auto-Reply Engine: Detected reply from lead @{raw_username} (ID: {sender_id}, log: {log_id})!")

                    if auto_reply_already_sent:
                        self.redis_conn.set(done_key, "1", ex=86400 * 30)
                        return

                    if not auto_reply_enabled or not auto_reply_text:
                        logging.info("Auto-Reply Engine: Auto-reply disabled or text unset. user_replied recorded.")
                        return

                    # ── Multi-Tier Safety Guard Check ────────────────────────
                    is_killed, kill_reason = is_kill_switch_active(self.redis_conn)
                    if is_killed or not is_outreach_enabled(self.redis_conn) or is_dry_run(self.redis_conn):
                        logging.info(f"Auto-Reply Engine: Outbound dispatch blocked by safety gate (kill_switch={is_killed}, reason={kill_reason}). Skipping 2nd message.")
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

                    # Send second message
                    media_files = self._resolve_media(auto_reply_media)
                    if media_files:
                        if len(media_files) == 1:
                            await client.send_message(event.chat_id, auto_reply_text, file=media_files[0])
                        else:
                            await client.send_file(event.chat_id, media_files, caption=auto_reply_text)
                    else:
                        await client.send_message(event.chat_id, auto_reply_text)

                    cur.execute("""
                        UPDATE campaign_logs 
                        SET auto_reply_sent = TRUE, 
                            auto_reply_sent_at = NOW(), 
                            auto_reply_error = NULL 
                        WHERE id = %s;
                    """, (log_id,))
                    conn.commit()

                    self.redis_conn.set(done_key, "1", ex=86400 * 30)
                    logging.info(f"Auto-Reply Engine: Successfully sent 2nd message to @{raw_username} (ID: {sender_id})!")

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
        Safety fallback dispatcher (runs every 60 seconds):
        Queries DB for leads where user_replied = TRUE but auto_reply_sent = FALSE.
        Ensures delivery even if messages arrived while worker was restarting.
        """
        logging.info("Auto-Reply fallback dispatcher task started.")
        while not self.shutdown_event.is_set():
            try:
                await asyncio.sleep(60)
                if not self.user_client or not self.user_client.is_connected():
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
                          AND cl.sent_at >= NOW() - INTERVAL '24 hours'
                        ORDER BY cl.sent_at ASC
                        LIMIT 5;
                    """)
                    unreplied_leads = cur.fetchall()

                    for row in unreplied_leads:
                        log_id = row['log_id']
                        target = row['telegram_user_id'] or row['contact_username']
                        if not target:
                            continue

                        lock_key = f"autoreply_lock:{target}"
                        if not self.redis_conn.set(lock_key, "1", nx=True, ex=30):
                            continue

                        try:
                            peer = await self.user_client.get_input_entity(target)
                            logging.info(f"Auto-Reply Fallback: Sending 2nd message to {target} (log {log_id})...")
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
                            self.redis_conn.set(f"autoreply_done:{target}", "1", ex=86400 * 30)
                            logging.info(f"Auto-Reply Fallback: Successfully sent 2nd message to {target}!")
                            await asyncio.sleep(random.randint(5, 10))

                        except errors.FloodWaitError as fw:
                            logging.warning(f"Auto-Reply Fallback FloodWait: {fw.seconds}s.")
                            await asyncio.sleep(fw.seconds)
                            break
                        except Exception as send_err:
                            logging.error(f"Auto-Reply Fallback error sending to {target}: {send_err}")
                            cur.execute("UPDATE campaign_logs SET auto_reply_error = %s WHERE id = %s", (str(send_err), log_id))
                            conn.commit()

            except Exception as fb_err:
                logging.debug(f"Auto-reply fallback note: {fb_err}")
