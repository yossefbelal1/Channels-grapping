import os
import sys
import re
import json
import asyncio
import signal
import logging
from dotenv import load_dotenv
import redis
from telethon import events, errors
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from tg_manager import TelegramManager
from validator import DatabaseHelper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Regex to broadly match Telegram links (t.me/... or telegram.me/...)
TELEGRAM_LINK_REGEX = re.compile(
    r'(?:https?://)?(?:t\.me|telegram\.me)/(?:joinchat/)?\+?[a-zA-Z0-9_.-]+',
    re.IGNORECASE
)

# Regex to match mentions/usernames (e.g. @username)
USERNAME_REGEX = re.compile(r'@([a-zA-Z0-9_]{5,32})')

def parse_telegram_link(link: str):
    """
    Parses a Telegram link and returns a tuple (link_type, identifier).
    link_type can be 'public' or 'private'.
    For 'public', identifier is the username.
    For 'private', identifier is the invite hash.
    Returns (None, None) if parsing fails.
    """
    link = link.strip()
    
    # Check for private invite links with '+' prefix (e.g. t.me/+hash)
    private_plus_match = re.search(r'(?:t\.me|telegram\.me)/\+([a-zA-Z0-9_-]+)', link, re.IGNORECASE)
    if private_plus_match:
        return 'private', private_plus_match.group(1)
        
    # Check for private invite links with 'joinchat' prefix
    private_joinchat_match = re.search(r'(?:t\.me|telegram\.me)/joinchat/([a-zA-Z0-9_-]+)', link, re.IGNORECASE)
    if private_joinchat_match:
        return 'private', private_joinchat_match.group(1)
        
    # Public link: t.me/username
    public_match = re.search(r'(?:t\.me|telegram\.me)/([a-zA-Z0-9_]{5,32})', link, re.IGNORECASE)
    if public_match:
        username = public_match.group(1)
        username_lower = username.lower()
        
        # Avoid matching common Telegram subpaths, email domains, reserved words, and bots
        junk_usernames = {
            'joinchat', 'share', 'addstickers', 'addlist', 'gmail', 'hotmail', 'yahoo', 'outlook',
            'icloud', 'mail', 'yandex', 'protonmail', 'proton', 'telegram', 'spambot', 'sticker',
            'gif', 'bot', 'username', 'ads', 'advertise', 'channel', 'group', 'chat', 'support',
            'help', 'admin', 'contact', 'info', 'service', 'feedback', 'terms', 'privacy'
        }
        
        if username_lower not in junk_usernames:
            # Skip usernames ending in "bot" or "_bot" to avoid resolving bots
            if not (username_lower.endswith('bot') or username_lower.endswith('_bot')):
                return 'public', username
            
    return None, None

def normalize_telegram_link(link: str) -> str:
    """
    Normalizes different Telegram link variations into a standard https://t.me/... format.
    """
    clean_link = link.strip()
    # Remove protocol prefix
    if clean_link.lower().startswith("https://"):
        clean_link = clean_link[8:]
    elif clean_link.lower().startswith("http://"):
        clean_link = clean_link[7:]
        
    # Standardize domain
    if clean_link.lower().startswith("telegram.me/"):
        clean_link = "t.me/" + clean_link[12:]
        
    # Re-prep protocol
    if not clean_link.lower().startswith("t.me/"):
        return f"https://t.me/{clean_link}"
    
    return f"https://{clean_link}"

async def join_group(tg_manager: TelegramManager, session_name: str, link: str, shutdown_event: asyncio.Event) -> bool:
    """
    Attempts to join a group/channel through Centralized Telegram Manager with daily limits.
    """
    link_type, identifier = parse_telegram_link(link)
    if not link_type:
        logging.error(f"Unsupported or invalid Telegram link format: {link}")
        return False
        
    # Check and enforce strict daily join limit (max 5 joins per account per day)
    redis_conn = tg_manager.redis_conn
    joins_key = f"health:{session_name}:joins_today"
    joins_today = int(redis_conn.get(joins_key) or 0)
    if joins_today >= 5:
        logging.warning(f"Session {session_name} has reached the daily group join limit ({joins_today}/5). Skipping join to prevent bans.")
        return False
        
    try:
        joined_successfully = False
        if link_type == 'public':
            async def public_join(cl):
                logging.info(f"Stealth joining public group: @{identifier}")
                await cl(JoinChannelRequest(identifier))
                return True
            joined_successfully = await tg_manager.execute_request(session_name, public_join, shutdown_event=shutdown_event)
        elif link_type == 'private':
            async def private_join(cl):
                logging.info(f"Stealth joining private group with hash: {identifier}")
                await cl(ImportChatInviteRequest(identifier))
                return True
            joined_successfully = await tg_manager.execute_request(session_name, private_join, shutdown_event=shutdown_event)
            
        if joined_successfully:
            # Increment and set 24h expiry
            redis_conn.incr(joins_key)
            redis_conn.expire(joins_key, 86400)
            logging.info(f"Stealth join successful for {session_name}. Daily joins count: {int(redis_conn.get(joins_key) or 0)}/5.")
            return True
        return False
            
    except errors.UserAlreadyParticipantError:
        logging.info(f"Already a member of group: {link}")
        return True
    except Exception as e:
        logging.error(f"Failed to join group {link}: {e}")
        return False

async def slow_joiner_task(tg_manager: TelegramManager, redis_conn: redis.Redis, session_name: str, shutdown_event: asyncio.Event):
    """
    Background Task 1: Pops one group link from 'discovered_groups' list every 12 hours and joins it.
    Uses dynamic session rotation from the active accounts pool.
    """
    logging.info("Slow Joiner background task initialized.")
    join_interval = int(os.getenv("JOIN_INTERVAL_SECONDS", 3600)) # Default 1 hour
    empty_list_sleep = 60 # Check Redis every 60 seconds if queue is empty
    import time
    
    while not shutdown_event.is_set():
        try:
            # Select healthiest available session in the pool that has < 5 joins today and is not rate-limited
            active_session = None
            best_score = -1
            for name in list(tg_manager.clients.keys()):
                if tg_manager.is_account_banned(name):
                    continue
                until_ts = redis_conn.get(f"health:{name}:rate_limited_until:join")
                if until_ts:
                    try:
                        if time.time() < float(until_ts):
                            continue
                    except ValueError:
                        pass
                until_ts_gen = redis_conn.get(f"health:{name}:rate_limited_until")
                if until_ts_gen:
                    try:
                        if time.time() < float(until_ts_gen):
                            continue
                    except ValueError:
                        pass
                joins_today = int(redis_conn.get(f"health:{name}:joins_today") or 0)
                if joins_today >= 5:
                    continue
                score = tg_manager.get_health_score(name)
                if score > best_score:
                    best_score = score
                    active_session = name

            if not active_session:
                logging.warning("No healthy/available Telegram accounts in the pool can perform joins right now. Waiting 10 minutes...")
                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=600)
                except asyncio.TimeoutError:
                    pass
                continue
                
            # Pop one link from Redis List (LPOP)
            raw_link = redis_conn.lpop("discovered_groups")
            
            if raw_link:
                try:
                    data = json.loads(raw_link)
                    link = data["link"]
                    source = data.get("source", "unknown")
                    method = data.get("method", "telegram_search")
                    keyword = data.get("keyword", "")
                except (json.JSONDecodeError, TypeError, KeyError):
                    link = raw_link
                    source = "unknown"
                    method = "telegram_search"
                    keyword = ""
                
                logging.info(f"Popped link from queue to join: {link}. Selected active session: '{active_session}'")
                success = await join_group(tg_manager, active_session, link, shutdown_event)
                
                if success:
                    # Resolve priority queue dynamically based on marketplace_score
                    link_type, identifier = parse_telegram_link(link)
                    group_username = identifier if (link_type == 'public' and identifier) else f"group_{abs(hash(link))}"
                    group_score = int(redis_conn.get(f"mkt:score:{group_username}") or 0)
                    
                    queue_name = "queue:normal"
                    if group_score > 80:
                        queue_name = "queue:critical"
                    elif group_score > 60:
                        queue_name = "queue:high"
                    elif group_score > 40:
                        queue_name = "queue:normal"
                    else:
                        queue_name = "queue:low"
                        
                    payload = json.dumps({
                        "link": link,
                        "source": source,
                        "method": "marketplace_group" if method == "telegram_search" else method,
                        "keyword": keyword
                    })
                    redis_conn.rpush(queue_name, payload)
                    logging.info(f"Join successful. Queued group {link} to priority {queue_name} (Score: {group_score}%). Sleeping for {join_interval}s before next join...")
                    try:
                        await asyncio.wait_for(shutdown_event.wait(), timeout=join_interval)
                    except asyncio.TimeoutError:
                        pass
                else:
                    logging.warning("Join failed. Cooling down for 10 minutes before checking queue...")
                    try:
                        await asyncio.wait_for(shutdown_event.wait(), timeout=600)
                    except asyncio.TimeoutError:
                        pass
            else:
                # Queue empty, wait a minute before checking again
                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=empty_list_sleep)
                except asyncio.TimeoutError:
                    pass
                    
        except Exception as e:
            logging.error(f"Error in Slow Joiner loop: {e}", exc_info=True)
            await asyncio.sleep(10)

async def leave_rejected_groups_loop(tg_manager: TelegramManager, redis_conn: redis.Redis, shutdown_event: asyncio.Event):
    """
    Periodically checks for groups in rejected_groups_set and leaves them to prevent queue flooding.
    """
    logging.info("Leave Rejected Groups background task initialized.")
    while not shutdown_event.is_set():
        try:
            # Fetch rejected groups from Redis
            rejected_groups = redis_conn.smembers("rejected_groups_set")
            if rejected_groups:
                for session_name, client in tg_manager.clients.items():
                    if not client.is_connected():
                        continue
                    try:
                        dialogs = await client.get_dialogs()
                        for dialog in dialogs:
                            if dialog.is_group:
                                entity = dialog.entity
                                username = getattr(entity, 'username', None)
                                # Check if group username is rejected
                                is_rejected = False
                                if username and username.lower() in rejected_groups:
                                    is_rejected = True
                                
                                if is_rejected:
                                    logging.info(f"Radar client leaving rejected/non-forex group: @{username or entity.id}")
                                    try:
                                        await client(LeaveChannelRequest(entity))
                                        logging.info(f"Successfully left group: @{username or entity.id}")
                                    except Exception as le:
                                        logging.error(f"Error leaving group @{username or entity.id}: {le}")
                    except Exception as d_err:
                        logging.error(f"Error retrieving dialogs for session {session_name}: {d_err}")
        except Exception as e:
            logging.error(f"Error in leave_rejected_groups_loop: {e}")
            
        # Run every 10 minutes
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=600)
        except asyncio.TimeoutError:
            pass

def setup_listener_task(tg_manager: TelegramManager, redis_conn: redis.Redis, db_helper: DatabaseHelper):
    """
    Background Task 2 (The Listener): Listens for incoming messages in all groups, 
    extracts links/mentions, filters duplicates using Redis Set, and pushes to validation queue.
    Also calculates dynamic marketplace scoring and updates the channel graph.
    """
    # Enforces priority routing based on keywords
    high_value_kws = ["vip", "premium", "اشتراك", "ادارة", "نسخ", "funded"]
    
    # Register message handler on ALL active accounts in the pool
    for session_name, client in tg_manager.clients.items():
        @client.on(events.NewMessage)
        async def new_message_handler(event):
            # Exclude private chats and broadcast channels
            if not event.is_group:
                return
                
            text = event.raw_text
            if not text:
                return
                
            # Dynamic Marketplace Group Scoring
            try:
                chat = await event.get_chat()
                group_username = getattr(chat, 'username', None)
                if not group_username:
                    group_username = f"group_{abs(event.chat_id)}"
            except Exception:
                group_username = f"group_{abs(event.chat_id)}"
                chat = None
                
            # If the group is rejected, ignore the message and do not process anything
            if group_username and redis_conn.sismember("rejected_groups_set", group_username.lower()):
                return
                
            # Track message counts in Redis
            total_msgs = redis_conn.incr(f"mkt:msg_count:{group_username}")
            
            # Extract links and mentions for current message to compute scores
            links_in_msg = len(TELEGRAM_LINK_REGEX.findall(text))
            
            raw_mentions = USERNAME_REGEX.findall(text)
            mentions_in_msg = sum(1 for m in raw_mentions if m.lower() not in ('joinchat', 'share', 'addstickers', 'addlist'))
            
            is_promo_msg = any(kw in text.lower() for kw in high_value_kws)
            
            if mentions_in_msg > 0:
                redis_conn.incrby(f"mkt:mentions_count:{group_username}", mentions_in_msg)
            if links_in_msg > 0:
                redis_conn.incrby(f"mkt:links_count:{group_username}", links_in_msg)
            if is_promo_msg:
                redis_conn.incr(f"mkt:ad_count:{group_username}")
                
            sender_id = getattr(event, 'sender_id', None)
            if sender_id and (mentions_in_msg > 0 or links_in_msg > 0 or is_promo_msg):
                redis_conn.sadd(f"mkt:promoters:{group_username}", str(sender_id))
                
            # Calculate and save score every 30 messages
            if total_msgs >= 30:
                mentions_count = int(redis_conn.get(f"mkt:mentions_count:{group_username}") or 0)
                links_count = int(redis_conn.get(f"mkt:links_count:{group_username}") or 0)
                ad_count = int(redis_conn.get(f"mkt:ad_count:{group_username}") or 0)
                unique_promoters = redis_conn.scard(f"mkt:promoters:{group_username}") or 0
                
                member_count = 0
                if chat:
                    try:
                        member_count = getattr(chat, 'participants_count', 0) or 0
                        if not member_count:
                            member_count = getattr(await event.client.get_entity(chat), 'participants_count', 0) or 0
                    except Exception:
                        pass
                
                # Formula based on mentions, links, ads, activity level, unique promoters, and member count
                score = 0
                if total_msgs > 0:
                    promo_ratio = (mentions_count * 1.0 + links_count * 1.5 + ad_count * 2.0) / total_msgs
                    promoter_ratio = unique_promoters / total_msgs
                    score = int(promo_ratio * 70 + promoter_ratio * 20)
                
                # Member count boost (up to 10 points)
                if member_count > 50000:
                    score += 10
                elif member_count > 20000:
                    score += 7
                elif member_count > 5000:
                    score += 4
                    
                mkt_score = min(100, max(0, score))
                
                # Resolve group ID in leads table
                group_id = db_helper.insert_stub_lead(group_username)
                
                if group_id:
                    # Update member count in leads
                    if member_count > 0:
                        with db_helper.conn.cursor() as cur:
                            cur.execute("UPDATE leads SET member_count = %s WHERE id = %s", (member_count, group_id))
                    
                    # Update group metrics in database
                    db_helper.upsert_group_metrics(group_id, total_msgs, mentions_count, links_count, ad_count, mkt_score)
                
                redis_conn.set(f"mkt:score:{group_username}", mkt_score)
                
                # Reset counters
                redis_conn.delete(f"mkt:msg_count:{group_username}")
                redis_conn.delete(f"mkt:mentions_count:{group_username}")
                redis_conn.delete(f"mkt:links_count:{group_username}")
                redis_conn.delete(f"mkt:ad_count:{group_username}")
                redis_conn.delete(f"mkt:promoters:{group_username}")
                
            # Check priority and group score
            group_score = int(redis_conn.get(f"mkt:score:{group_username}") or 0)
            is_high_priority = any(kw in text.lower() for kw in high_value_kws) or group_score > 60
            
            # Extract links and mentions
            links_found = TELEGRAM_LINK_REGEX.findall(text)
            mentions_found = USERNAME_REGEX.findall(text)
            
            discovered_in_msg = {} # target_username_lower -> (target_username, normalized_link, rel_type)
            
            # 1. Process links
            for link in links_found:
                clean_link = link.rstrip('.,;)!"\'')
                if not clean_link:
                    continue
                normalized_link = normalize_telegram_link(clean_link)
                target_type, target_username = parse_telegram_link(normalized_link)
                if target_type == 'public' and target_username:
                    rel_type = 'advertisement' if is_high_priority else 'link'
                    discovered_in_msg[target_username.lower()] = (target_username, normalized_link, rel_type)
                    
            # 2. Process mentions
            for mention in mentions_found:
                if mention.lower() not in ('joinchat', 'share', 'addstickers', 'addlist'):
                    normalized_link = f"https://t.me/{mention}"
                    rel_type = 'advertisement' if is_high_priority else 'mention'
                    if mention.lower() not in discovered_in_msg:
                        discovered_in_msg[mention.lower()] = (mention, normalized_link, rel_type)
                        
            # Now queue and insert to graph
            for target_username_lower, (target_username, normalized_link, rel_type) in discovered_in_msg.items():
                is_seen = redis_conn.sismember("seen_channels", normalized_link)
                
                # Expose matched keywords if any
                matched_kws = [kw for kw in high_value_kws if kw in text.lower()]
                keyword_val = matched_kws[0] if matched_kws else ""
                
                method_val = "advertisement" if rel_type == "advertisement" else "group_mention"
                
                if not is_seen:
                    queue_name = "queue:high" if is_high_priority else "queue:normal"
                    redis_conn.sadd("seen_channels", normalized_link)
                    payload = json.dumps({
                        "link": normalized_link,
                        "source": group_username,
                        "method": method_val,
                        "keyword": keyword_val
                    })
                    redis_conn.rpush(queue_name, payload)
                    logging.info(f"Stealth radar detected link: {normalized_link} (Routed to priority list: {queue_name} from group @{group_username} with score {group_score}%)")
                    
                # Graph database edge insertion
                try:
                    source_id = db_helper.insert_stub_lead(group_username)
                    if source_id:
                        with db_helper.conn.cursor() as cur:
                            cur.execute("UPDATE leads SET is_group = TRUE WHERE id = %s", (source_id,))
                            
                    target_id = db_helper.insert_stub_lead(target_username)
                    if target_id and source_id:
                        db_helper.insert_relationship(source_id, target_id, rel_type)
                        logging.info(f"Graph edge added recursively from Radar: @{group_username} -> @{target_username} ({rel_type})")
                except Exception as ge:
                    logging.error(f"Error updating channel graph relation: {ge}")

async def main():
    load_dotenv()
    
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    redis_db = int(os.getenv("REDIS_DB", 0))
    redis_password = os.getenv("REDIS_PASSWORD", None)
    
    session_radar = os.getenv("SESSION_RADAR", "radar_session")
    
    # Establish Redis connection
    logging.info(f"Connecting to Redis at {redis_host}:{redis_port}...")
    try:
        redis_conn = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True
        )
        redis_conn.ping()
        logging.info("Redis connection established.")
    except Exception as e:
        logging.error(f"Failed to connect to Redis: {e}")
        sys.exit(1)
        
    # Initialize Central Telegram Manager
    logging.info("Initializing Telegram Manager pool...")
    tg_manager = TelegramManager(redis_conn, session_name=session_radar, worker_type="radar")
    await tg_manager.start_all()
    
    # Initialize Database Helper
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = int(os.getenv("DB_PORT", 5432))
    db_name = os.getenv("DB_NAME", "leadhunter_db")
    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD", "leadhunter_pass")
    
    logging.info("Connecting to Database...")
    db_helper = DatabaseHelper(db_host, db_port, db_name, db_user, db_password)
    
    try:
        # Register the message listener across all clients
        setup_listener_task(tg_manager, redis_conn, db_helper)
        
        shutdown_event = asyncio.Event()
        
        # Graceful shutdown handler
        def trigger_shutdown():
            logging.info("Shutdown signal received. Cleaning up...")
            shutdown_event.set()
            
        loop = asyncio.get_running_loop()
        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, trigger_shutdown)
        except NotImplementedError:
            pass
            
        # Shutdown watcher to cleanly stop the Telethon client when event fires
        async def watch_shutdown():
            await shutdown_event.wait()
            logging.info("Disconnecting clients...")
            await tg_manager.disconnect_all()
            
        # Run background tasks concurrently
        joiner_task = asyncio.create_task(slow_joiner_task(tg_manager, redis_conn, session_radar, shutdown_event))
        leave_task = asyncio.create_task(leave_rejected_groups_loop(tg_manager, redis_conn, shutdown_event))
        watcher_task = asyncio.create_task(watch_shutdown())
        
        # Block main thread until watcher task signals disconnection
        # Run client loops indefinitely
        await asyncio.gather(
            *[client.run_until_disconnected() for client in tg_manager.clients.values()],
            return_exceptions=True
        )
        
        # Ensure joiner task is cancelled and cleaned up
        joiner_task.cancel()
        leave_task.cancel()
        watcher_task.cancel()
        
    except (KeyboardInterrupt, asyncio.CancelledError):
        logging.info("Interrupted. Shutting down...")
    finally:
        await tg_manager.disconnect_all()
        redis_conn.close()
        logging.info("Worker A (The Radar) has stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Process terminated. Exiting.")
    except Exception as e:
        logging.critical(f"FATAL WORKER ERROR: {e}", exc_info=True)
        sys.exit(1)
