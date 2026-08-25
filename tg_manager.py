import os
import json
import random
import time
import asyncio
import logging
from datetime import datetime, timezone
import redis
from telethon import TelegramClient, errors

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

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
        # Fall back to root directory if 'sessions/' is not writable
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
    Manages rate limits, dynamic health scoring, adaptive jitter, and automatic failovers.
    """
    def __init__(self, redis_conn: redis.Redis, session_name: str = None, worker_type: str = None):
        self.redis_conn = redis_conn
        self.session_name = session_name
        self.worker_type = worker_type
        self.accounts = []
        self.clients = {}
        # Store unique lock value to prevent active instances from deleting/extending newer locks
        self.lock_value = f"pid_{os.getpid()}_rand_{random.randint(1000, 9999)}_time_{datetime.now(timezone.utc).isoformat()}"
        self.load_account()

    def load_account(self):
        """
        Loads the assigned session + any backup accounts of the same worker type from accounts.json.
        Backup accounts are identified by role field: backup_<session_type>.
        This enables automatic rotation when the primary account is banned or rate-limited.
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

        # Determine worker type from session name if not explicitly passed (e.g. validator_session → validator)
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
            # Fallback to .env
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

        # Validate all loaded accounts
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
            
            # Resolve safe writable path for the SQLite session file
            session_path = get_session_path(session_name)
            client = TelegramClient(session_path, api_id, api_hash)
            client.flood_sleep_threshold = 120
            self.clients[session_name] = client
            
            # Initialize health state in Redis if not exists
            if not self.redis_conn.exists(f"health:{session_name}:score"):
                self.redis_conn.set(f"health:{session_name}:score", 100) # Start fully healthy (100)
                self.redis_conn.set(f"health:{session_name}:joins_today", 0)

    async def acquire_lock(self, session_name: str):
        """
        Acquires a Redis-based distributed lock for the session to prevent concurrent access.
        """
        lock_key = f"lock:session:{session_name}"
        # Set lock with a 60 seconds expiry if not exists
        success = self.redis_conn.set(lock_key, self.lock_value, ex=60, nx=True)
        if not success:
            current_owner = self.redis_conn.get(lock_key)
            raise RuntimeError(
                f"SESSION CONCURRENCY LOCK ERROR: Telethon session '{session_name}' is already opened "
                f"by another worker instance ({current_owner}). Access denied to prevent SQLite corruption."
            )
        logging.info(f"Successfully acquired session lock for '{session_name}'.")
        self.heartbeat_task = asyncio.create_task(self.lock_heartbeat_loop(lock_key))

    async def lock_heartbeat_loop(self, lock_key: str):
        """
        Periodically extends the session lock TTL while the worker is active, validating ownership.
        """
        while True:
            try:
                await asyncio.sleep(20)
                current_owner = self.redis_conn.get(lock_key)
                if current_owner == self.lock_value:
                    self.redis_conn.expire(lock_key, 60)
                else:
                    logging.warning(f"Lock heartbeat ownership mismatch. Found '{current_owner}', expected '{self.lock_value}'. Stopping heartbeat.")
                    break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error in lock heartbeat loop: {e}")
                await asyncio.sleep(5)

    def release_lock(self, session_name: str):
        """
        Releases the session lock in Redis only if this instance owns it.
        """
        if hasattr(self, 'heartbeat_task') and self.heartbeat_task:
            self.heartbeat_task.cancel()
        lock_key = f"lock:session:{session_name}"
        current_owner = self.redis_conn.get(lock_key)
        if current_owner == self.lock_value:
            self.redis_conn.delete(lock_key)
            logging.info(f"Released session lock for '{session_name}'.")
        else:
            logging.warning(f"Did not release lock for '{session_name}' because owner is '{current_owner}' (we are '{self.lock_value}').")

    async def health_recovery_loop(self):
        """
        Periodically recovers health scores of all sessions (adds +5 health every 10 minutes).
        """
        while True:
            try:
                await asyncio.sleep(600) # Sleep 10 minutes
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
        Connects and authenticates the primary client. Backups are connected dynamically on demand.
        """
        await self.initialize_clients()

        # ── Fresh-start cleanup: clear stale locks, rate limits & reset health for primary session only ──
        primary_session = self.session_name
        lock_key = f"lock:session:{primary_session}"
        if self.redis_conn.exists(lock_key):
            self.redis_conn.delete(lock_key)
            logging.info(f"🧹 Cleared stale session lock for primary session '{primary_session}' on fresh startup.")

        stale_key = f"health:{primary_session}:rate_limited_until"
        if self.redis_conn.exists(stale_key):
            self.redis_conn.delete(stale_key)
            logging.info(f"🧹 Cleared stale rate-limit key for primary session '{primary_session}' on fresh startup.")
        
        # Reset health to 100 on fresh startup
        self.redis_conn.set(f"health:{primary_session}:score", 100)
        logging.info(f"Health score for primary session '{primary_session}' reset to 100 on startup.")

        # Connect ONLY the primary session on startup
        primary_session = self.session_name
        client = self.clients.get(primary_session)
        if not client:
            raise RuntimeError(f"Primary session '{primary_session}' client not initialized.")

        try:
            await self.acquire_lock(primary_session)
            logging.info(f"Connecting Telethon client primary session: {primary_session}...")
            await client.connect()
            authorized = await client.is_user_authorized()
            if not authorized:
                raise RuntimeError(
                    f"TELEGRAM AUTHENTICATION ERROR: Primary session '{primary_session}' is not authorized. "
                    f"Please run the bootstrap login script ('python login.py') on the host to authenticate."
                )
            logging.info(f"Starting Telethon client primary session: {primary_session}...")
            await client.start()
            logging.info(f"Primary client {primary_session} started and authenticated successfully.")
        except Exception as e:
            logging.error(f"Failed to start primary client {primary_session}: {e}")
            try:
                if client.is_connected():
                    await client.disconnect()
            except Exception as disc_err:
                logging.warning(f"Error disconnecting primary client {primary_session} after failed startup: {disc_err}")
            self.release_lock(primary_session)
            self.redis_conn.set(f"health:{primary_session}:score", 0)
            raise e  # Fail worker startup

        # Start health recovery background task background task
        asyncio.create_task(self.health_recovery_loop())

    async def disconnect_all(self):
        """
        Gracefully disconnects all client sessions and releases locks.
        """
        for session_name, client in list(self.clients.items()):
            if client.is_connected():
                logging.info(f"Disconnecting client: {session_name}...")
                await client.disconnect()
            self.release_lock(session_name)
        self.clients.clear()

    def get_health_score(self, session_name: str) -> int:
        """
        Retrieves health score from Redis, defaulting to 100.
        """
        score = self.redis_conn.get(f"health:{session_name}:score")
        if score is None:
            return 100
        return int(score)

    def update_health_score(self, session_name: str, delta: int):
        """
        Modifies account health score (capped between 0 and 100).
        """
        current = self.get_health_score(session_name)
        new_score = min(100, max(0, current + delta))
        self.redis_conn.set(f"health:{session_name}:score", new_score)
        logging.info(f"Account {session_name} health score updated: {current} -> {new_score}")

    async def sleep_adaptive_jitter(self, session_name: str, shutdown_event: asyncio.Event):
        """
        Calculates and sleeps an adaptive jitter delay based on account health.
        """
        health = self.get_health_score(session_name)
        
        # Decide delay ranges based on health tiers
        if health >= 80:
            jitter = random.randint(4, 8) # Normal delay (sustainable rate to prevent FloodWait)
        elif health >= 50:
            jitter = random.randint(5, 10) # Reduced load
            logging.warning(f"Account {session_name} is under load (Health: {health}). Extending jitter to {jitter}s...")
        elif health >= 30:
            jitter = random.randint(10, 25) # Cooldown mode
            logging.warning(f"Account {session_name} is in cooldown mode (Health: {health}). Extending jitter to {jitter}s...")
        else:
            jitter = random.randint(25, 60) # High restrictions
            logging.warning(f"Account {session_name} is critically restricted (Health: {health}). Extending jitter to {jitter}s...")
            
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=jitter)
        except asyncio.TimeoutError:
            pass

    def check_request_limit(self, session_name: str) -> bool:
        """
        Enforces a hard limit of max 800 requests per hour per account in Redis.
        """
        key = f"limit:{session_name}:requests_hour"
        count = self.redis_conn.get(key)
        
        if count is not None and int(count) >= 300:
            return False
            
        # Increment request counter and set expiry if new
        pipe = self.redis_conn.pipeline()
        pipe.incr(key)
        if count is None:
            pipe.expire(key, 3600) # Expires in 1 hour
        pipe.execute()
        return True

    def get_healthiest_session(self, preferred_session: str = None) -> str:
        """
        Finds the healthiest available session name. Falls back from preferred if unhealthy or rate-limited.
        """
        # Helper to check if a session is currently rate limited
        def is_session_rate_limited(name: str) -> bool:
            until_ts = self.redis_conn.get(f"health:{name}:rate_limited_until")
            if until_ts:
                try:
                    if time.time() < float(until_ts):
                        return True
                except ValueError:
                    pass
            return False

        # If preferred is healthy (>=30) and not rate-limited, use it
        if preferred_session and preferred_session in self.clients:
            if self.get_health_score(preferred_session) >= 30 and not is_session_rate_limited(preferred_session):
                return preferred_session

        # Find healthiest across all clients that are not rate-limited
        best_session = None
        best_score = -1

        for name in self.clients.keys():
            if is_session_rate_limited(name):
                continue
            score = self.get_health_score(name)
            if score > best_score:
                best_score = score
                best_session = name

        if best_session and best_score >= 30:
            return best_session

        # If all are rate-limited/disabled, fallback to preferred if available
        if preferred_session and preferred_session in self.clients:
            return preferred_session
        return best_session or (list(self.clients.keys())[0] if self.clients else None)

    def mark_account_banned(self, session_name: str):
        """
        Marks an account as permanently banned in Redis.
        Sets health to 0 and records ban timestamp.
        """
        self.redis_conn.set(f"health:{session_name}:score", 0)
        self.redis_conn.set(f"health:{session_name}:banned", "1", ex=86400 * 30)  # 30 days
        logging.critical(f"🚨 ACCOUNT BANNED: Session '{session_name}' marked as permanently banned. Will rotate to backup.")

    def is_account_banned(self, session_name: str) -> bool:
        """Returns True if this account is marked as banned in Redis."""
        return self.redis_conn.get(f"health:{session_name}:banned") == "1"

    async def execute_request(self, preferred_session: str, request_func, *args, **kwargs):
        """
        Orchestrates an API call: performs account failover, checks rate limits,
        applies adaptive jitter, handles rate limit backoffs, retries, and
        auto-rotates to backup accounts on permanent bans.
        """
        shutdown_event = kwargs.pop('shutdown_event', asyncio.Event())
        attempted = kwargs.get('_attempted_sessions', set())

        # Select healthiest session that has not been attempted yet in this request
        session_name = None
        best_score = -1
        for name in list(self.clients.keys()):
            if name in attempted:
                continue
            # Check Redis rate limit cache
            until_ts = self.redis_conn.get(f"health:{name}:rate_limited_until")
            is_limited = False
            if until_ts:
                try:
                    if time.time() < float(until_ts):
                        is_limited = True
                except ValueError:
                    pass
            if is_limited:
                continue
            
            # Check Redis concurrency lock
            lock_key = f"lock:session:{name}"
            if self.redis_conn.exists(lock_key) and not self.clients[name].is_connected():
                continue
            
            score = self.get_health_score(name)
            if score > best_score:
                best_score = score
                session_name = name

        # Fallback to preferred or any session if all are attempted/limited
        if not session_name:
            session_name = preferred_session if preferred_session not in attempted else None
            if not session_name:
                for name in list(self.clients.keys()):
                    if name not in attempted:
                        session_name = name
                        break
            if not session_name:
                raise RuntimeError("No configured Telegram clients are available or all connection attempts failed.")

        client = self.clients.get(session_name)
        if not client:
            raise RuntimeError(f"No client found for session '{session_name}'.")

        # Track that we are attempting this session
        attempted.add(session_name)
        kwargs['_attempted_sessions'] = attempted
        kwargs['shutdown_event'] = shutdown_event

        # ── DYNAMIC CONNECTION FOR BACKUPS ──
        if not client.is_connected():
            logging.info(f"⚡ Connecting dynamically to backup session: '{session_name}'...")
            try:
                await self.acquire_lock(session_name)
                await client.connect()
                authorized = await client.is_user_authorized()
                if not authorized:
                    raise RuntimeError(f"Backup session '{session_name}' is not authorized.")
                await client.start()
                logging.info(f"⚡ Backup client '{session_name}' started and authenticated successfully.")
            except Exception as conn_err:
                logging.error(f"Failed to connect dynamically to backup session '{session_name}': {conn_err}")
                try:
                    if client.is_connected():
                        await client.disconnect()
                except Exception:
                    pass
                self.release_lock(session_name)
                # Temporarily disable this session in Redis by setting health score to 0
                # only if the connection error is NOT a concurrency lock error
                if "lock" not in str(conn_err).lower():
                    self.redis_conn.set(f"health:{session_name}:score", 0)
                # Failover: recursively find another healthy session
                return await self.execute_request(preferred_session, request_func, *args, **kwargs)

        if session_name != preferred_session:
            logging.info(f"⚡ Auto-routing from '{preferred_session}' → '{session_name}' (health-based failover).")

        retries = 0
        max_retries = 3

        while retries < max_retries and not shutdown_event.is_set():
            # Check if this session is currently cached as rate-limited in Redis
            until_ts = self.redis_conn.get(f"health:{session_name}:rate_limited_until")
            if until_ts:
                try:
                    diff = float(until_ts) - time.time()
                    if diff > 0:
                        logging.warning(f"Session {session_name} is in cache rate-limit for another {diff:.1f}s. Rotating...")
                        # Recursively find another healthy session
                        return await self.execute_request(preferred_session, request_func, *args, **kwargs)
                except ValueError:
                    pass

            # Check Redis request hourly limits
            if not self.check_request_limit(session_name):
                logging.warning(f"Hourly request limit reached for {session_name}. Caching limit and rotating...")
                # Cache rate-limit expiration for 60 seconds in Redis to prevent picking it again immediately
                self.redis_conn.set(f"health:{session_name}:rate_limited_until", time.time() + 60, ex=60)
                # Recursively failover to another healthy session
                return await self.execute_request(preferred_session, request_func, *args, **kwargs)

            # Apply adaptive jitter sleep
            await self.sleep_adaptive_jitter(session_name, shutdown_event)
            if shutdown_event.is_set():
                return None

            try:
                logging.info(f"Executing request using session '{session_name}'...")
                # Filter out internal kwargs so they don't pollute the client request call
                target_kwargs = kwargs.copy()
                target_kwargs.pop('_attempted_sessions', None)
                target_kwargs.pop('shutdown_event', None)
                res = await request_func(client, *args, **target_kwargs)
                self.update_health_score(session_name, 1)
                return res

            except errors.FloodWaitError as e:
                self.update_health_score(session_name, -20)
                if e.seconds > 300:
                    logging.warning(f"Severe FloodWaitError ({e.seconds}s) on session {session_name} for a specific request. Caching limit in Redis and raising immediately.")
                    # Cache rate-limit expiration timestamp in Redis
                    self.redis_conn.set(f"health:{session_name}:rate_limited_until", time.time() + e.seconds, ex=e.seconds)
                    raise e
                
                wait_time = e.seconds + 10
                logging.warning(f"FloodWaitError: Session {session_name} rate limited for {e.seconds}s. Sleeping {wait_time}s...")
                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=wait_time)
                except asyncio.TimeoutError:
                    pass
                retries += 1

            except (errors.UserDeactivatedBanError, errors.AuthKeyUnregisteredError,
                    errors.AuthKeyInvalidError, errors.SessionRevokedError) as e:
                # ── PERMANENT BAN / AUTH REVOKE ─────────────────────────────────
                self.mark_account_banned(session_name)
                logging.critical(f"🚨 Session '{session_name}' is permanently banned/revoked: {e}")
                # Try to find a healthy backup immediately by recursively calling execute_request
                return await self.execute_request(preferred_session, request_func, *args, **kwargs)

            except errors.RPCError as e:
                # Rpc call failure
                logging.warning(f"RPC call failed on session {session_name}: {e}")
                raise e

            except (ValueError, TypeError) as e:
                # Username does not exist, type cast error, or format is invalid
                logging.warning(f"Entity not found, invalid type, or invalid format on session {session_name}: {e}")
                raise e

            except Exception as e:
                # Catch public request-to-join error and treat as successful request
                if "successfully requested to join" in str(e) or "InviteRequestSent" in type(e).__name__:
                    logging.info(f"Stealth join request sent successfully (pending approval) on session {session_name}.")
                    self.update_health_score(session_name, 1)
                    return True

                logging.error(f"Telegram API exception on session {session_name}: {e}")
                self.update_health_score(session_name, -5)
                backoff = 2 ** retries * 5
                logging.info(f"Backing off for {backoff} seconds before retry...")
                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=backoff)
                except asyncio.TimeoutError:
                    pass
                retries += 1

        raise RuntimeError(f"Request failed after {max_retries} attempts on session {session_name}.")
