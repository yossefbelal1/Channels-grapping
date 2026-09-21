"""
app/discovery/similar_channels_crawler.py — Telegram Similar Channels Recommendation Spiderweb Crawler

Utilizes Telegram's native `channels.getChannelRecommendations` API to spiderweb-crawl
related Forex channels from verified seeds, while extracting pinned messages and direct contacts.

Rotates across auxiliary research sessions (acc_12723433281, acc_14809564829, radar_session)
preserving user_session (@tamerads1) exclusively for safe campaign outreach.
"""

import os
import sys
import json
import re
import asyncio
import logging
from typing import Dict, Any, List, Optional, Tuple, Set
from datetime import datetime, timezone
from telethon import TelegramClient, errors
from telethon.tl.functions.channels import GetFullChannelRequest, GetChannelRecommendationsRequest

from app.core.db import get_db_connection
from app.core.redis_client import get_redis_client
from app.validator.contact_extractor import extract_contacts

logger = logging.getLogger("similar_channels_crawler")
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

API_ID = int(os.getenv("TELEGRAM_API_ID", "39064636"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "72d90d8ac46e9293e3d5254d9645e4f9")
SESSION_DIR = os.getenv("TELEGRAM_SESSIONS_DIR", "/app/sessions" if os.path.exists("/app/sessions") else "sessions")

# Default research account pool (NEVER include user_session / @tamerads1 here)
RESEARCH_SESSIONS = [
    "acc_12723433281",
    "acc_14809564829",
    "radar_session"
]

USERNAME_CLEAN_RE = re.compile(r'^[a-zA-Z0-9_]{4,32}$')


class SimilarChannelsCrawler:
    """
    Spiderweb crawler leveraging Telegram channel recommendations and pinned message mining.
    """

    def __init__(self, sessions: Optional[List[str]] = None):
        self.sessions = sessions or RESEARCH_SESSIONS
        self.session_index = 0
        self.clients: Dict[str, TelegramClient] = {}
        self.active_campaign_id: Optional[str] = None
        self._load_active_campaign()

    def _load_active_campaign(self):
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM campaigns WHERE status = 'active' ORDER BY created_at DESC LIMIT 1;")
                row = cur.fetchone()
                if row:
                    self.active_campaign_id = str(row['id'])
                    logger.info(f"Loaded active campaign ID: {self.active_campaign_id}")
            conn.close()
        except Exception as e:
            logger.warning(f"Could not load active campaign: {e}")

    def _get_next_session(self) -> str:
        sname = self.sessions[self.session_index % len(self.sessions)]
        self.session_index += 1
        return sname

    async def get_client(self, session_name: str) -> Optional[TelegramClient]:
        if session_name in self.clients:
            client = self.clients[session_name]
            if client.is_connected():
                return client

        spath = os.path.join(SESSION_DIR, session_name)
        client = TelegramClient(spath, API_ID, API_HASH)
        try:
            await client.connect()
            if await client.is_user_authorized():
                self.clients[session_name] = client
                return client
            else:
                logger.warning(f"Session {session_name} is not authorized.")
                await client.disconnect()
                return None
        except Exception as e:
            logger.warning(f"Failed to connect session {session_name}: {e}")
            return None

    async def close_all(self):
        for sname, client in self.clients.items():
            try:
                if client.is_connected():
                    await client.disconnect()
            except Exception:
                pass
        self.clients.clear()

    async def inspect_and_expand_channel(
        self,
        target_username: str,
        depth: int = 0,
        max_recs: int = 15
    ) -> Dict[str, Any]:
        """
        Inspects channel, extracts pinned messages, mines contacts, auto-enrolls,
        and retrieves similar channel recommendations.
        """
        clean_user = target_username.strip().lstrip('@')
        result = {
            "channel_username": clean_user,
            "title": "",
            "members": 0,
            "pinned_text": "",
            "contacts": {},
            "recommendations": [],
            "enrolled": False,
            "error": None
        }

        # Try sessions with round-robin failover
        client = None
        for _ in range(len(self.sessions)):
            sname = self._get_next_session()
            client = await self.get_client(sname)
            if client:
                break

        if not client:
            result["error"] = "No authorized research session available"
            logger.error(result["error"])
            return result

        try:
            # 1. Resolve entity
            entity = await client.get_entity(clean_user)
            title = getattr(entity, 'title', clean_user) or clean_user
            result["title"] = title

            # 2. Fetch Full Channel info (for pinned_msg_id and participants_count)
            full = await client(GetFullChannelRequest(entity))
            full_chat = getattr(full, 'full_chat', None)
            members = getattr(full_chat, 'participants_count', 0) or getattr(entity, 'participants_count', 0) or 0
            about = getattr(full_chat, 'about', '') or ''
            pinned_msg_id = getattr(full_chat, 'pinned_msg_id', None)
            result["members"] = members

            # 3. Pinned Message Extraction
            pinned_text = ""
            if pinned_msg_id:
                try:
                    pinned_msg = await client.get_messages(entity, ids=pinned_msg_id)
                    if pinned_msg and pinned_msg.message:
                        pinned_text = pinned_msg.message
                        result["pinned_text"] = pinned_text
                        logger.info(f"[@{clean_user}] Fetched Pinned Message (ID: {pinned_msg_id}, {len(pinned_text)} chars)")
                except Exception as p_err:
                    logger.warning(f"Could not fetch pinned message for @{clean_user}: {p_err}")

            # 4. Extract Structured Contacts (prioritizing pinned text)
            contacts = extract_contacts(text="", description=about, channel_username=clean_user, pinned_text=pinned_text)
            result["contacts"] = contacts
            contact_user = contacts.get('contact_username')
            admin_user = contacts.get('admin_username')
            owner_user = contacts.get('owner_username')
            wa = contacts.get('whatsapp')

            logger.info(f"[@{clean_user}] Contacts Extracted: Contact=@{contact_user} | Admin=@{admin_user} | WhatsApp={wa}")

            # 5. Update leads record in PostgreSQL
            self._update_channel_record(clean_user, title, members, about, contacts)

            # 6. Auto-enroll into campaign if qualified with contact
            if self.active_campaign_id and contact_user:
                enrolled = self._auto_enroll_channel(clean_user, title, members, contact_user)
                result["enrolled"] = enrolled

            # 7. Fetch Telegram Similar Channels (Recommendations)
            logger.info(f"[@{clean_user}] Querying Telegram Similar Channels...")
            try:
                recs = await client(GetChannelRecommendationsRequest(channel=entity))
                chats = getattr(recs, 'chats', [])
                logger.info(f"[@{clean_user}] Received {len(chats)} similar channel recommendations.")

                r_client = get_redis_client()
                rec_candidates = []

                for chat in chats[:max_recs]:
                    r_username = getattr(chat, 'username', None)
                    r_title = getattr(chat, 'title', '')
                    r_members = getattr(chat, 'participants_count', 0) or 0

                    if not r_username or not USERNAME_CLEAN_RE.match(r_username):
                        continue

                    # Ingest candidate into leads table & Redis queue:high
                    self._ingest_recommended_channel(
                        channel_username=r_username,
                        title=r_title,
                        member_count=r_members,
                        source_username=clean_user,
                        depth=depth + 1,
                        r_client=r_client
                    )
                    rec_candidates.append({
                        "username": r_username,
                        "title": r_title,
                        "members": r_members
                    })

                result["recommendations"] = rec_candidates

            except errors.FloodWaitError as fwe:
                logger.warning(f"FloodWait on session when fetching recommendations for @{clean_user}: {fwe.seconds}s")
            except Exception as r_err:
                logger.warning(f"Could not fetch recommendations for @{clean_user}: {r_err}")

        except errors.UsernameNotOccupiedError:
            logger.warning(f"Channel @{clean_user} does not exist.")
            result["error"] = "not_found"
        except errors.ChannelPrivateError:
            logger.warning(f"Channel @{clean_user} is private.")
            result["error"] = "private"
        except Exception as e:
            logger.error(f"Error inspecting @{clean_user}: {e}", exc_info=True)
            result["error"] = str(e)

        return result

    def _update_channel_record(
        self,
        username: str,
        title: str,
        members: int,
        description: str,
        contacts: Dict[str, Any]
    ):
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE leads
                    SET title = COALESCE(NULLIF(%s, ''), title),
                        member_count = GREATEST(member_count, %s),
                        description = COALESCE(NULLIF(%s, ''), description),
                        contact_username = COALESCE(NULLIF(%s, ''), contact_username),
                        admin_username = COALESCE(NULLIF(%s, ''), admin_username),
                        owner_username = COALESCE(NULLIF(%s, ''), owner_username),
                        whatsapp = COALESCE(NULLIF(%s, ''), whatsapp),
                        last_scan = NOW()
                    WHERE channel_username = %s;
                """, (
                    title, members, description,
                    contacts.get('contact_username'),
                    contacts.get('admin_username'),
                    contacts.get('owner_username'),
                    contacts.get('whatsapp'),
                    username
                ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to update lead record for @{username}: {e}")

    def _auto_enroll_channel(self, username: str, title: str, members: int, contact: str) -> bool:
        if not self.active_campaign_id:
            return False
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                # Get lead ID
                cur.execute("SELECT id, lead_score FROM leads WHERE channel_username = %s;", (username,))
                row = cur.fetchone()
                if not row:
                    conn.close()
                    return False

                lead_id = row['id']
                score = row['lead_score'] or 80

                # Priority: P0 (VIP / high member count), P1 (Active Forex), P2 (Normal)
                priority = 'P1'
                if members >= 20000 or score >= 90:
                    priority = 'P0'
                elif members < 2000:
                    priority = 'P2'

                # Enroll lead if not already enrolled
                cur.execute("""
                    INSERT INTO campaign_logs (
                        id, campaign_id, lead_id, status, priority, priority_score, priority_reason, commercial_fit_score
                    )
                    SELECT gen_random_uuid(), %s, %s, 'approved', %s, %s, 'Spiderweb Pinned Contact Auto-Enrolled', %s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM campaign_logs cl
                        JOIN leads l ON cl.lead_id = l.id
                        WHERE LOWER(l.contact_username) = LOWER(%s)
                           OR cl.lead_id = %s
                    );
                """, (self.active_campaign_id, lead_id, priority, score, score, contact, lead_id))
                enrolled = cur.rowcount > 0
                if enrolled:
                    logger.info(f"[@{username}] Auto-enrolled into active campaign {self.active_campaign_id} (Priority: {priority}, Contact: @{contact})")
            conn.commit()
            conn.close()
            return enrolled
        except Exception as e:
            logger.error(f"Failed to auto-enroll @{username}: {e}")
            return False

    def _ingest_recommended_channel(
        self,
        channel_username: str,
        title: str,
        member_count: int,
        source_username: str,
        depth: int,
        r_client
    ):
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO leads (
                        channel_username, title, member_count, discovery_source, discovery_method, depth, status, discovered_at, last_scan
                    )
                    VALUES (%s, %s, %s, %s, 'similar_channel', %s, 'new', NOW(), NOW())
                    ON CONFLICT (channel_username) DO UPDATE SET
                        title = COALESCE(NULLIF(EXCLUDED.title, ''), leads.title),
                        member_count = GREATEST(leads.member_count, EXCLUDED.member_count),
                        discovery_source = COALESCE(leads.discovery_source, EXCLUDED.discovery_source);
                """, (channel_username, title, member_count, source_username, depth))
            conn.commit()
            conn.close()

            # Push to queue:high in Redis for deep validation
            if r_client:
                is_seen = r_client.sismember("seen_channels", f"https://t.me/{channel_username}")
                if not is_seen:
                    r_client.sadd("seen_channels", f"https://t.me/{channel_username}")
                    payload = json.dumps({
                        "link": f"https://t.me/{channel_username}",
                        "source": source_username,
                        "method": "similar_channel",
                        "depth": depth
                    })
                    r_client.rpush("queue:high", payload)
                    logger.info(f"  -> Discovered Similar Channel: @{channel_username} ({title}, {member_count} members) -> Pushed to queue:high")
        except Exception as e:
            logger.warning(f"Failed to ingest recommended channel @{channel_username}: {e}")

    async def spiderweb_crawl(self, seed_usernames: List[str], max_depth: int = 2) -> Dict[str, Any]:
        """
        Runs a multi-hop BFS spiderweb crawl from given seed channels.
        """
        visited: Set[str] = set()
        queue: List[Tuple[str, int]] = [(s.strip().lstrip('@'), 0) for s in seed_usernames if s]

        stats = {
            "seeds": seed_usernames,
            "inspected_channels": 0,
            "pinned_messages_found": 0,
            "contacts_extracted": 0,
            "campaign_auto_enrolled": 0,
            "similar_channels_discovered": 0
        }

        while queue:
            current_user, depth = queue.pop(0)
            if current_user.lower() in visited:
                continue
            visited.add(current_user.lower())

            logger.info(f"\n🕷️ Spiderweb Hop [Depth {depth}]: Inspecting @{current_user}...")
            res = await self.inspect_and_expand_channel(current_user, depth=depth)

            stats["inspected_channels"] += 1
            if res.get("pinned_text"):
                stats["pinned_messages_found"] += 1
            if res.get("contacts", {}).get("contact_username"):
                stats["contacts_extracted"] += 1
            if res.get("enrolled"):
                stats["campaign_auto_enrolled"] += 1

            recs = res.get("recommendations", [])
            stats["similar_channels_discovered"] += len(recs)

            if depth < max_depth:
                for r in recs:
                    r_user = r["username"].lower()
                    if r_user not in visited and len(queue) < 100:
                        queue.append((r["username"], depth + 1))

            # Small polite pause to preserve Telethon quota
            await asyncio.sleep(2.0)

        await self.close_all()
        return stats


if __name__ == "__main__":
    seeds = sys.argv[1:] if len(sys.argv) > 1 else ["AlmaalFOREX", "SarhanIndicators"]
    crawler = SimilarChannelsCrawler()
    summary = asyncio.run(crawler.spiderweb_crawl(seed_usernames=seeds, max_depth=1))
    print("\n================ SPIDERWEB CRAWL COMPLETE ================")
    print(json.dumps(summary, indent=2))
    print("==========================================================")
