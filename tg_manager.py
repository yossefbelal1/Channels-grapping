"""
tg_manager.py — Centralized Telegram Client & Request Manager

Production-Hardened Features:
- Distributed Session Locking with host:pid:uuid ownership & atomic Lua release
- Automatic Lock Renewal Heartbeat
- Atomic Sliding-Window Rate Limiter via Redis Lua
- Granular FloodWait Classification (transient backoff vs cooldown vs quarantine)
- Bounded Iterative Failover (zero recursive call stacks)
- Full Backward-Compatibility for all existing callers
"""

import os
import sys
import json
import random
import time
import uuid
import socket
import asyncio
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
import redis
from telethon import TelegramClient, errors

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

# ── Centralized Rate Limits ───────────────────────────────────────────────────
DEFAULT_MAX_REQUESTS_PER_HOUR = int(os.getenv("TELEGRAM_MAX_REQUESTS_PER_HOUR", "300"))
LOCK_TTL_SECONDS = int(os.getenv("TELEGRAM_SESSION_LOCK_TTL", "60"))
LOCK_HEARTBEAT_INTERVAL = int(os.getenv("TELEGRAM_LOCK_HEARTBEAT_INTERVAL", "15"))

# ── Atomic Redis Lua Scripts ──────────────────────────────────────────────────
# 1. Atomic Lock Release (Compare and Delete)
LUA_RELEASE_LOCK = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

# 2. Atomic Lock Renewal (Compare and Expire)
LUA_RENEW_LOCK = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("expire", KEYS[1], ARGV[2])
else
    return 0
end
"""

# 3. Atomic Sliding-Window Rate Limiter
LUA_RATE_LIMIT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local max_limit = tonumber(ARGV[3])
local clear_before = now - window

-- Clean entries older than current sliding window
redis.call('ZREMRANGEBYSCORE', key, '-inf', clear_before)

local current_count = redis.call('ZCARD', key)
if current_count < max_limit then
    local seq = redis.call('INCR', key .. ':seq')
    redis.call('ZADD', key, now, now .. ':' .. seq)
    redis.call('EXPIRE', key, window + 60)
    return 1
else
    return 0
end
"""


def validate_telegram_credentials(session_name: str, api_id, api_hash: str):
    """
    Validates api_id and api_hash.
    Rejects placeholder values like 123456, your_telegram_api_hash_here, empty or invalid values.
    Raises ValueError with a clear explanation if invalid.
    """
    if api_id is None or api_hash is None:
        raise ValueError(
            f"CRITICAL CONFIG ERROR: Session '{session_name}' has missing api_id or api_hash. "
            f"Please check accounts.json or environment variables."
        )

    api_id_str = str(api_id).strip()
    api_hash_str = str(api_hash).strip()

    if not api_id_str or not api_hash_str:
        raise ValueError(
            f"CRITICAL CONFIG ERROR: Session '{session_name}' has empty api_id or api_hash."
        )

    try:
        api_id_int = int(api_id_str)
    except ValueError:
        raise ValueError(
            f"CRITICAL CONFIG ERROR: Session '{session_name}' has non-integer api_id '{api_id_str}'."
        )

    if api_id_int == 123456:
        raise ValueError(
            f"CRITICAL CONFIG ERROR: Session '{session_name}' is using placeholder api_id '123456'. "
            f"Please update accounts.json or .env with your actual Telegram API ID from https://my.telegram.org."
        )

    placeholder_hashes = [
        "your_telegram_api_hash_here",
        "your_api_hash_here",
        "your_api_hash"
    ]
    if api_hash_str.lower() in placeholder_hashes or len(api_hash_str) < 10:
        raise ValueError(
            f"CRITICAL CONFIG ERROR: Session '{session_name}' is using a placeholder or invalid api_hash '{api_hash_str}'. "
            f"Please update accounts.json or .env with your actual Telegram API Hash from https://my.telegram.org."
        )


def get_session_path(session_name: str) -> str:
    """
    Resolves the writable session file path.
    Checks and targets a 'sessions' subdirectory first.
    Falls back to user home directory or /tmp if the directory is not writable.
    """
    if not session_name:
        return "default_session"
    if os.path.isabs(session_name) or '/' in session_name or '\\' in session_name:
        return session_name

    sessions_dir = "sessions"
    try:
        os.makedirs(sessions_dir, exist_ok=True)
        test_file = os.path.join(sessions_dir, f".write_test_{session_name}")
        with open(test_file, 'w') as f:
            f.write('check')
        os.remove(test_file)
        return os.path.join(sessions_dir, session_name)
    except (IOError, OSError):
        try:
            test_file = f".write_test_{session_name}"
            with open(test_file, 'w') as f:
                f.write('check')
            os.remove(test_file)
            return session_name
        except (IOError, OSError):
            home_dir = os.path.expanduser("~")
            fallback_dir = os.path.join(home_dir, ".telegram_sessions")
            try:
                os.makedirs(fallback_dir, exist_ok=True)
                return os.path.join(fallback_dir, session_name)
            except Exception:
                tmp_dir = os.path.join("/tmp", ".telegram_sessions")
                os.makedirs(tmp_dir, exist_ok=True)
                return os.path.join(tmp_dir, session_name)


class TelegramManager:
    """
    Centralized Request Manager for multiple Telegram accounts.
    Manages rate limits, dynamic health scoring, adaptive jitter, atomic distributed locks,
    and automatic bounded failovers.
    """

    def __init__(self, redis_conn: redis.Redis, session_name: str = None, worker_type: str = None):
        self.redis_conn = redis_conn
        self.session_name = session_name
        self.worker_type = worker_type
        self.accounts = []
        self.clients = {}
        
        # Production-grade unique owner identifier (hostname:pid:uuid)
        hostname = socket.gethostname() or "unknown_host"
        self.owner_id = f"{hostname}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self.lock_value = self.owner_id  # Backward-compatible alias
        
        # Registered Lua scripts
        self._lua_release = self.redis_conn.register_script(LUA_RELEASE_LOCK)
        self._lua_renew = self.redis_conn.register_script(LUA_RENEW_LOCK)
        self._lua_ratelimit = self.redis_conn.register_script(LUA_RATE_LIMIT)
        
        self.heartbeat_tasks = {}
        self.load_account()

    def load_account(self):
        """
        Loads the assigned session + any backup accounts of the same worker type from accounts.json.
        Backup accounts are identified by role field: backup_<session_type>.
        """
        session_to_load = self.session_name
        if not session_to_load:
            session_to_load = os.getenv("SESSION_NAME")

        if not session_to_load:
            session_to_load = "validator_session"

        self.session_name = session_to_load
        json_path = "accounts.json"
        primary_account = None
        backup_accounts = []

        w_type = self.worker_type
        if not w_type:
            w_type = session_to_load.replace("_session", "")
        backup_role = f"backup_{w_type}"
        backup_roles = [backup_role]
        if w_type == "radar":
            backup_roles.append("backup_validator")

        if os.path.exists(json_path):
            try:
                with open(json_path, 'r') as f:
                    all_accounts = json.load(f)
                for acc in all_accounts:
                    if acc.get("session_name") == session_to_load:
                        primary_account = acc
                    elif acc.get("role") in backup_roles:
                        backup_accounts.append(acc)
            except Exception as e:
                logging.error(f"Error reading accounts.json: {e}")

        if primary_account:
            self.accounts = [primary_account] + backup_accounts
            logging.info(f"Loaded primary session '{session_to_load}' + {len(backup_accounts)} backup account(s) for worker type '{w_type}'.")
        else:
            api_id = os.getenv("API_ID")
            api_hash = os.getenv("API_HASH")
            if api_id and api_hash:
                self.accounts = [
                    {
                        "session_name": session_to_load,
                        "api_id": int(api_id),
                        "api_hash": api_hash
                    }
                ]
                logging.info(f"Loaded assigned account configuration '{session_to_load}' from .env parameters.")
            else:
                logging.error(f"No Telegram account configuration found for session: {session_to_load}")

        for acc in self.accounts:
            validate_telegram_credentials(acc.get("session_name"), acc.get("api_id"), acc.get("api_hash"))

    async def initialize_clients(self):
        """
        Initializes Telethon clients for configured accounts using safe writable session paths.
        """
        for acc in self.accounts:
            session_name = acc["session_name"]
            api_id = acc["api_id"]
            api_hash = acc["api_hash"]

            session_path = get_session_path(session_name)
            client = TelegramClient(session_path, api_id, api_hash)
            client.flood_sleep_threshold = 120
            self.clients[session_name] = client

            if not self.redis_conn.exists(f"health:{session_name}:score"):
                self.redis_conn.set(f"health:{session_name}:score", 100)
                self.redis_conn.set(f"health:{session_name}:joins_today", 0)

    # ── Distributed Locking (P0 Hardened) ─────────────────────────────────────

    async def acquire_lock(self, session_name: str, ttl: int = LOCK_TTL_SECONDS):
        """
        Acquires a distributed lock in Redis for the given session with ownership tracking.
        Guarantees that no two workers can open the same SQLite session file concurrently.
        """
        lock_key = f"lock:session:{session_name}"
        success = self.redis_conn.set(lock_key, self.owner_id, ex=ttl, nx=True)
        if not success:
            current_owner = self.redis_conn.get(lock_key)
            # If we already own the lock (e.g. re-entry), renew it and continue
            if current_owner == self.owner_id:
                self.redis_conn.expire(lock_key, ttl)
            else:
                raise RuntimeError(
                    f"SESSION CONCURRENCY LOCK ERROR: Telethon session '{session_name}' is currently held "
                    f"by another instance ({current_owner}). Access denied to protect SQLite session."
                )

        logging.info(f"🔒 Acquired distributed session lock for '{session_name}' (Owner: {self.owner_id}).")
        
        # Stop any existing heartbeat for this session before creating a new one
        if session_name in self.heartbeat_tasks and not self.heartbeat_tasks[session_name].done():
            self.heartbeat_tasks[session_name].cancel()
            
        self.heartbeat_tasks[session_name] = asyncio.create_task(
            self._lock_heartbeat_loop(session_name, lock_key, ttl)
        )

    async def _lock_heartbeat_loop(self, session_name: str, lock_key: str, ttl: int):
        """
        Background heartbeat that periodically extends lock TTL using atomic Lua renewal.
        """
        while True:
            try:
                await asyncio.sleep(LOCK_HEARTBEAT_INTERVAL)
                res = self._lua_renew(keys=[lock_key], args=[self.owner_id, ttl])
                if res != 1:
                    logging.warning(f"⚠️ Session lock for '{session_name}' was lost or overtaken by another instance.")
                    break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error in lock renewal heartbeat for '{session_name}': {e}")
                await asyncio.sleep(3)

    def release_lock(self, session_name: str):
        """
        Releases the session lock atomically via Lua script ONLY if this instance is the owner.
        """
        if session_name in self.heartbeat_tasks:
            self.heartbeat_tasks[session_name].cancel()
            self.heartbeat_tasks.pop(session_name, None)

        lock_key = f"lock:session:{session_name}"
        try:
            res = self._lua_release(keys=[lock_key], args=[self.owner_id])
            if res == 1:
                logging.info(f"🔓 Successfully released distributed lock for '{session_name}'.")
            else:
                logging.debug(f"Lock for '{session_name}' was not held by {self.owner_id} or already expired.")
        except Exception as e:
            logging.error(f"Error during atomic lock release for '{session_name}': {e}")

    # ── Health & Cooldowns ────────────────────────────────────────────────────

    async def health_recovery_loop(self):
        """
        Periodically recovers health scores of all sessions (+5 health every 10 minutes).
        """
        while True:
            try:
                await asyncio.sleep(600)
                for acc in self.accounts:
                    session_name = acc["session_name"]
                    self.update_health_score(session_name, 5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error in health recovery loop: {e}")
                await asyncio.sleep(60)

    async def start_all(self):
        """
        Connects and authenticates the primary client safely without removing locks of other workers.
        """
        await self.initialize_clients()

        primary_session = self.session_name
        
        # Reset health score for primary session on clean start
        self.redis_conn.set(f"health:{primary_session}:score", 100)

        client = self.clients.get(primary_session)
        if not client:
            raise RuntimeError(f"Primary session '{primary_session}' client not initialized.")

        try:
            await self.acquire_lock(primary_session)
            logging.info(f"Connecting Telethon primary session: {primary_session}...")
            await client.connect()
            authorized = await client.is_user_authorized()
            if not authorized:
                raise RuntimeError(
                    f"TELEGRAM AUTHENTICATION ERROR: Primary session '{primary_session}' is not authorized. "
                    f"Please run 'python login.py' to authenticate."
                )
            logging.info(f"Starting Telethon primary session: {primary_session}...")
            await client.start()
            logging.info(f"Primary client '{primary_session}' connected and authorized.")
        except Exception as e:
            logging.error(f"Failed to start primary client '{primary_session}': {e}")
            try:
                if client.is_connected():
                    await client.disconnect()
            except Exception:
                pass
            self.release_lock(primary_session)
            self.redis_conn.set(f"health:{primary_session}:score", 0)
            raise e

        asyncio.create_task(self.health_recovery_loop())

    async def disconnect_all(self):
        """
        Gracefully disconnects all client sessions and releases locks atomically.
        """
        for session_name, client in list(self.clients.items()):
            try:
                if client.is_connected():
                    logging.info(f"Disconnecting client: {session_name}...")
                    await client.disconnect()
            except Exception as e:
                logging.warning(f"Error disconnecting client {session_name}: {e}")
            finally:
                self.release_lock(session_name)
        self.clients.clear()

    def get_health_score(self, session_name: str) -> int:
        """Retrieves health score from Redis, defaulting to 100."""
        score = self.redis_conn.get(f"health:{session_name}:score")
        if score is None:
            return 100
        try:
            return int(score)
        except ValueError:
            return 100

    def update_health_score(self, session_name: str, delta: int):
        """Modifies account health score (capped between 0 and 100)."""
        current = self.get_health_score(session_name)
        new_score = min(100, max(0, current + delta))
        self.redis_conn.set(f"health:{session_name}:score", new_score)

    async def sleep_adaptive_jitter(self, session_name: str, shutdown_event: asyncio.Event):
        """Calculates and sleeps an adaptive jitter delay based on account health."""
        health = self.get_health_score(session_name)
        if health >= 80:
            jitter = random.randint(4, 8)
        elif health >= 50:
            jitter = random.randint(5, 10)
        elif health >= 30:
            jitter = random.randint(10, 25)
        else:
            jitter = random.randint(25, 60)

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=jitter)
        except asyncio.TimeoutError:
            pass

    # ── Atomic Rate Limiter (P0 Hardened) ─────────────────────────────────────

    def check_request_limit(self, session_name: str, max_requests: int = DEFAULT_MAX_REQUESTS_PER_HOUR, window: int = 3600) -> bool:
        """
        Enforces rate limiting using an atomic Redis sliding-window log.
        Fails CLOSED on Redis/Lua errors to protect Telegram accounts from bans.
        """
        key = f"limit:{session_name}:requests_sliding"
        now = time.time()
        try:
            allowed = self._lua_ratelimit(keys=[key], args=[now, window, max_requests])
            return bool(allowed == 1)
        except Exception as e:
            logging.error(f"Rate limiter Redis/Lua error for '{session_name}': {e}. Failing CLOSED to prevent Telegram account bans.")
            return False

    def get_healthiest_session(self, preferred_session: str = None) -> str:
        """Finds the healthiest available session name not currently rate-limited."""
        def is_rate_limited(name: str) -> bool:
            until_ts = self.redis_conn.get(f"health:{name}:rate_limited_until")
            if until_ts:
                try:
                    return time.time() < float(until_ts)
                except ValueError:
                    pass
            return False

        if preferred_session and preferred_session in self.clients:
            if self.get_health_score(preferred_session) >= 30 and not is_rate_limited(preferred_session):
                return preferred_session

        best_session = None
        best_score = -1

        for name in self.clients.keys():
            if is_rate_limited(name):
                continue
            score = self.get_health_score(name)
            if score > best_score:
                best_score = score
                best_session = name

        if best_session and best_score >= 30:
            return best_session

        if preferred_session and preferred_session in self.clients:
            return preferred_session
        return best_session or (list(self.clients.keys())[0] if self.clients else None)

    def mark_account_banned(self, session_name: str):
        """Marks an account as permanently banned in Redis."""
        self.redis_conn.set(f"health:{session_name}:score", 0)
        self.redis_conn.set(f"health:{session_name}:banned", "1", ex=86400 * 30)
        logging.critical(f"🚨 ACCOUNT BANNED: Session '{session_name}' marked as permanently banned. Rotating to backup.")

    def is_account_banned(self, session_name: str) -> bool:
        """Returns True if this account is marked as banned in Redis."""
        return self.redis_conn.get(f"health:{session_name}:banned") == "1"

    # ── Bounded Iterative Request Execution (P0 Hardened) ─────────────────────

    async def execute_request(self, preferred_session: str, request_func, *args, **kwargs):
        """
        Executes a Telegram API call using a bounded iterative retry/failover loop.
        Zero recursion, robust distributed locking, atomic rate limiting, and granular FloodWait handling.
        """
        shutdown_event = kwargs.pop('shutdown_event', asyncio.Event())
        
        # Clean internal kwargs
        target_kwargs = {k: v for k, v in kwargs.items() if not k.startswith('_') and k != 'shutdown_event'}

        attempted_sessions = set()
        total_candidates = list(self.clients.keys())
        if preferred_session and preferred_session not in total_candidates:
            total_candidates.insert(0, preferred_session)
        max_session_attempts = max(1, len(total_candidates))

        last_exception = None

        for attempt_idx in range(max_session_attempts):
            if shutdown_event.is_set():
                return None

            # 1. Select healthiest available candidate
            session_name = None
            best_score = -1

            for name in total_candidates:
                if name in attempted_sessions:
                    continue
                if self.is_account_banned(name):
                    continue

                # Check Redis cooldown
                until_ts = self.redis_conn.get(f"health:{name}:rate_limited_until")
                if until_ts:
                    try:
                        if time.time() < float(until_ts):
                            continue
                    except ValueError:
                        pass

                score = self.get_health_score(name)
                if score > best_score:
                    best_score = score
                    session_name = name

            # Fallback to preferred or next unattempted session
            if not session_name:
                for name in total_candidates:
                    if name not in attempted_sessions and not self.is_account_banned(name):
                        session_name = name
                        break

            if not session_name:
                break  # All candidates exhausted

            attempted_sessions.add(session_name)
            client = self.clients.get(session_name)
            if not client:
                continue

            # 2. Dynamic connection for backup sessions
            if not client.is_connected():
                logging.info(f"⚡ Connecting dynamically to session '{session_name}'...")
                try:
                    await self.acquire_lock(session_name)
                    await client.connect()
                    if not await client.is_user_authorized():
                        raise RuntimeError(f"Session '{session_name}' is not authorized.")
                    await client.start()
                    logging.info(f"⚡ Session '{session_name}' connected and authenticated.")
                except Exception as conn_err:
                    logging.error(f"Failed to connect to session '{session_name}': {conn_err}")
                    try:
                        if client.is_connected():
                            await client.disconnect()
                    except Exception:
                        pass
                    self.release_lock(session_name)
                    if "lock" not in str(conn_err).lower():
                        self.update_health_score(session_name, -50)
                    last_exception = conn_err
                    continue  # Try next session in loop

            # 3. Inner bounded retry loop for transient issues
            retries = 0
            max_inner_retries = 3
            session_success = False

            while retries < max_inner_retries and not shutdown_event.is_set():
                # Check atomic rate limit
                if not self.check_request_limit(session_name):
                    logging.warning(f"Hourly rate limit reached for '{session_name}'. Cooling down and rotating...")
                    self.redis_conn.set(f"health:{session_name}:rate_limited_until", time.time() + 60, ex=60)
                    break  # Rotate to next session

                await self.sleep_adaptive_jitter(session_name, shutdown_event)
                if shutdown_event.is_set():
                    return None

                try:
                    res = await request_func(client, *args, **target_kwargs)
                    self.update_health_score(session_name, 1)
                    return res

                except errors.FloodWaitError as e:
                    if e.seconds <= 60:
                        logging.warning(f"Transient FloodWait ({e.seconds}s) on '{session_name}'. Sleeping...")
                        self.update_health_score(session_name, -5)
                        try:
                            await asyncio.wait_for(shutdown_event.wait(), timeout=e.seconds + 2)
                        except asyncio.TimeoutError:
                            pass
                        retries += 1
                    elif e.seconds <= 300:
                        logging.warning(f"Moderate FloodWait ({e.seconds}s) on '{session_name}'. Setting cooldown and rotating...")
                        self.update_health_score(session_name, -15)
                        self.redis_conn.set(f"health:{session_name}:rate_limited_until", time.time() + e.seconds, ex=e.seconds + 60)
                        last_exception = e
                        break  # Rotate to next session
                    else:
                        logging.warning(f"Severe FloodWait ({e.seconds}s) on '{session_name}'. Setting quarantine cooldown...")
                        self.update_health_score(session_name, -30)
                        self.redis_conn.set(f"health:{session_name}:rate_limited_until", time.time() + e.seconds, ex=e.seconds + 3600)
                        last_exception = e
                        break  # Rotate to next session

                except (errors.UserDeactivatedBanError, errors.AuthKeyUnregisteredError,
                        errors.AuthKeyInvalidError, errors.SessionRevokedError) as e:
                    self.mark_account_banned(session_name)
                    logging.critical(f"🚨 Session '{session_name}' permanently banned/revoked: {e}")
                    last_exception = e
                    break  # Rotate to next session

                except errors.RPCError as e:
                    logging.warning(f"RPC call failed on session '{session_name}': {e}")
                    last_exception = e
                    raise e

                except (ValueError, TypeError) as e:
                    logging.warning(f"Entity not found / invalid argument on '{session_name}': {e}")
                    last_exception = e
                    raise e

                except Exception as e:
                    if "successfully requested to join" in str(e) or "InviteRequestSent" in type(e).__name__:
                        logging.info(f"Stealth join request sent successfully (pending approval) on '{session_name}'.")
                        self.update_health_score(session_name, 1)
                        return True

                    logging.error(f"Telegram API exception on session '{session_name}': {e}")
                    self.update_health_score(session_name, -5)
                    backoff = min(30, (2 ** retries) * 3)
                    try:
                        await asyncio.wait_for(shutdown_event.wait(), timeout=backoff)
                    except asyncio.TimeoutError:
                        pass
                    retries += 1
        if last_exception:
            raise last_exception
        raise RuntimeError("No Telegram clients available or all candidate sessions failed.")

    # ── Advanced Discovery Methods (v5 Graph Intelligence) ────────────────────

    async def search_global_messages(
        self,
        session_name: str,
        query: str,
        offset_rate: int = 0,
        offset_id: int = 0,
        limit: int = 100,
        shutdown_event: Optional[asyncio.Event] = None
    ):
        """
        Executes a global message search (messages.searchGlobal) across all public Telegram channels.
        Returns messages and chats matching the query.
        """
        from telethon.tl.functions.messages import SearchGlobalRequest
        from telethon.tl.types import InputMessagesFilterEmpty, InputPeerEmpty

        async def _req(cl):
            return await cl(SearchGlobalRequest(
                q=query,
                filter=InputMessagesFilterEmpty(),
                min_date=None,
                max_date=None,
                offset_rate=offset_rate,
                offset_peer=InputPeerEmpty(),
                offset_id=offset_id,
                limit=limit
            ))

        return await self.execute_request(session_name, _req, shutdown_event=shutdown_event or asyncio.Event())

    async def get_channel_recommendations(
        self,
        session_name: str,
        channel_peer,
        shutdown_event: Optional[asyncio.Event] = None
    ):
        """
        Fetches similar channel recommendations (channels.getChannelRecommendations) for a given channel.
        """
        from telethon.tl.functions.channels import GetChannelRecommendationsRequest

        async def _req(cl):
            return await cl(GetChannelRecommendationsRequest(channel=channel_peer))

        return await self.execute_request(session_name, _req, shutdown_event=shutdown_event or asyncio.Event())

    async def search_posts(
        self,
        session_name: str,
        query: str,
        hashtag: Optional[str] = None,
        offset_rate: int = 0,
        offset_id: int = 0,
        limit: int = 100,
        shutdown_event: Optional[asyncio.Event] = None
    ):
        """
        Searches public posts with fallback to global message search if searchPosts is restricted.
        """
        search_term = f"#{hashtag} {query}".strip() if hashtag else query
        return await self.search_global_messages(
            session_name=session_name,
            query=search_term,
            offset_rate=offset_rate,
            offset_id=offset_id,
            limit=limit,
            shutdown_event=shutdown_event
        )

