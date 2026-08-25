import os
import sys
import json
import asyncio
import signal
import logging
import random
from dotenv import load_dotenv
import redis
from telethon import functions, errors
from telethon.tl.types import Chat, Channel
from tg_manager import TelegramManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Refined search keywords — Arabic Forex & Crypto Business Intelligence targeting
KEYWORDS = [
    # --- مدرسة المفاهيم الحديثة (SMC / ICT Arabic / SEO Reconnaissance) ---
    "تحليل SMC", "كورس ICT", "سمارت موني", "اوردر بلوك", "Order Block عربي",
    "سيولة التداول", "Liquidity كريبتو", "تداول SMC", "مفهوم ICT", "هندسة السيولة",
    "Fair Value Gap", "FVG فوركس", "توصيات SMC", "صفقات ICT", "مفهوم المال الذكي", "توصيات الذهب", "XAUUSD",
    
    # --- فوركس وتداول عام بالهوية العربية ---
    "فوركس عرب", "عرب فوركس", "تداول العملات مصر", "فوركس الخليج", "عرب تداول",
    "مدرسة التداول", "المتداول العربي", "ديوان التداول", "عالم الفوركس", "ديلي فوركس",
    "توصيات فوركس", "تداول العملات", "وسيط فوركس مرخص", "حساب تجريبي", "الرافعة المالية", "التحليل الفني",
    
    # --- الكريبتو والعملات الرقمية النشطة ---
    "توصيات كريبتو", "تحليل البيتكوين", "صفقات سكالبينج", "منصة بينانس", "عملات رقمية",
    "توصيات Binance", "مستقبل الكريبتو", "إشارات كريبتو", "حيتان الكريبتو", "Whale Alert عربي",
    "صفقات فيوتشر", "Binance Futures عربي", "توصيات SOL", "تحليل BTC",
    "تحليل العملات", "بيتكوين", "تداول الكريبتو", "Whale Alert", "Liquidation", "SMC Crypto", "Binance Futures",
    
    # --- قنوات الـ VIP والاشتراكات والتحويلات ---
    "جروب VIP فوركس", "توصيات VIP مجانية", "Premium Signals كريبتو", "قناة اشتراك فوركس",
    "اشارات ذهب VIP", "توصيات مدفوعة", "VIP Crypto Trading", "وسيط معتمد", "رابط الإحالة", "الوسيط المعرف",
    "قناة VIP", "قناة اشتراك", "توصيات VIP",
    
    # --- إدارة الحسابات والنسخ والتمويل (Prop Firms) ---
    "إدارة حسابات فوركس", "ادارة حسابات تداول", "نسخ صفقات", "Copy Trading عربي",
    "حسابات ممولة", "شركات التمويل فوركس", "Funded Accounts عربي", "تحدي شركة تمويل",
    "تداول باير", "دفع USDT بينانس"
]

async def run_scavenger(tg_manager: TelegramManager, redis_conn: redis.Redis, session_name: str, shutdown_event: asyncio.Event):
    """
    Executes a single cycle of keyword searching and group/channel link extraction.
    Does NOT join any groups. Uses Centralized Request Manager.
    """
    logging.info("Starting scavenging cycle...")
    new_groups_found = 0
    new_channels_found = 0
    
    # Prioritize keywords from Redis (Phase 8 Learning) and shuffle to avoid bans
    prioritized_keywords = list(KEYWORDS)
    try:
        prioritized = redis_conn.zrevrange("priority:keywords", 0, -1)
        if prioritized:
            prioritized_keywords = list(prioritized)
            for kw in KEYWORDS:
                if kw not in prioritized_keywords:
                    prioritized_keywords.append(kw)
            logging.info("Prioritized search keywords loaded from Redis.")
    except Exception as redis_err:
        logging.warning(f"Failed to load prioritized keywords from Redis: {redis_err}")
        
    random.shuffle(prioritized_keywords)
    logging.info(f"Keywords shuffled for search cycle. Total keywords: {len(prioritized_keywords)}")
        
    for keyword in prioritized_keywords:
        if shutdown_event.is_set():
            break
            
        # Dynamically calculate delay based on session health score
        health = tg_manager.get_health_score(session_name)
        if health >= 80:
            delay = random.uniform(3, 7)
        elif health >= 50:
            delay = random.uniform(7, 15)
        elif health >= 30:
            delay = random.uniform(15, 30)
        else:
            delay = random.uniform(30, 60)
            
        logging.info(f"Session '{session_name}' health: {health}. Applying anti-ban jitter of {delay:.2f} seconds before searching '{keyword}'...")
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass
            
        if shutdown_event.is_set():
            break
            
        logging.info(f"Searching Telegram globally for keyword: '{keyword}'")
        try:
            # API Request wrapper
            async def search_request(cl):
                return await cl(functions.contacts.SearchRequest(q=keyword, limit=100))
                
            # Execute search through central request manager (enforcing jitter and limits)
            result = await tg_manager.execute_request(session_name, search_request, shutdown_event=shutdown_event)
            if not result:
                continue
                
            # Process search results
            for chat in result.chats:
                is_group = False
                
                # Check if the result is a Megagroup/Supergroup or small Group
                if isinstance(chat, Chat):
                    is_group = True
                elif isinstance(chat, Channel) and chat.megagroup:
                    is_group = True
                
                username = getattr(chat, 'username', None)
                if not username:
                    continue
                    
                if is_group:
                    group_link = f"https://t.me/{username}"
                    # Track all discovered groups and prevent duplicates
                    is_new = redis_conn.sadd("scavenged_groups_set", group_link)
                    if is_new:
                        # Push the new group link to the discovered_groups Redis list with source context
                        payload = json.dumps({
                            "link": group_link,
                            "source": keyword,
                            "method": "telegram_search",
                            "keyword": keyword
                        })
                        redis_conn.rpush("discovered_groups", payload)
                        logging.info(f"Discovered new group: {group_link} (Title: '{chat.title}', ID: {chat.id})")
                        new_groups_found += 1
                else:
                    # It's a channel - push directly to validation queue
                    channel_link = f"https://t.me/{username}"
                    is_new = redis_conn.sadd("seen_channels", channel_link)
                    if is_new:
                        payload = json.dumps({
                            "link": channel_link,
                            "source": keyword,
                            "method": "telegram_search",
                            "keyword": keyword
                        })
                        redis_conn.rpush("queue:normal", payload)
                        logging.info(f"Discovered new channel: {channel_link} (Title: '{chat.title}', ID: {chat.id}) - Queued for validation")
                        new_channels_found += 1
            
        except Exception as e:
            logging.error(f"Error searching for keyword '{keyword}': {e}", exc_info=True)
            
    logging.info(f"Scavenging cycle complete. Found {new_groups_found} new groups and {new_channels_found} new channels.")

async def main():
    load_dotenv()
    
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    redis_db = int(os.getenv("REDIS_DB", 0))
    redis_password = os.getenv("REDIS_PASSWORD", None)
    
    interval = int(os.getenv("SCAVENGER_INTERVAL_SECONDS", 86400))
    session_scavenger = os.getenv("SESSION_SCAVENGER", "scavenger_session")
    
    # Establish Redis connection
    logging.info(f"Connecting to Redis at {redis_host}:{redis_port} (DB: {redis_db})...")
    try:
        redis_conn = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True
        )
        redis_conn.ping()
        logging.info("Successfully connected to Redis.")
    except Exception as e:
        logging.error(f"Failed to connect to Redis: {e}")
        sys.exit(1)
        
    # Initialize Central Telegram Manager (bind specifically to scavenger session)
    logging.info(f"Initializing Telegram Manager for session: {session_scavenger}...")
    tg_manager = TelegramManager(redis_conn, session_name=session_scavenger, worker_type="scavenger")
    await tg_manager.start_all()
    
    shutdown_event = asyncio.Event()
    
    def stop_worker():
        logging.info("Graceful shutdown initiated...")
        shutdown_event.set()
        
    loop = asyncio.get_running_loop()
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_worker)
    except NotImplementedError:
        pass
        
    logging.info(f"Scavenger worker is active. Interval: {interval} seconds.")
    
    # Main Daily Loop
    while not shutdown_event.is_set():
        try:
            await run_scavenger(tg_manager, redis_conn, session_scavenger, shutdown_event)
        except Exception as e:
            logging.error(f"Unexpected error in main scavenger function: {e}", exc_info=True)
            
        logging.info(f"Sleeping for {interval} seconds until next scheduled search. Releasing session lock...")
        await tg_manager.disconnect_all()
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
            
        if not shutdown_event.is_set():
            logging.info("Waking up from scheduled sleep. Re-connecting Telegram client...")
            await tg_manager.start_all()
            
    # Disconnect active Telegram session
    await tg_manager.disconnect_all()
    redis_conn.close()
    logging.info("Worker C (The Scavenger) has stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Process interrupted by user. Exiting.")
    except Exception as e:
        logging.critical(f"FATAL WORKER ERROR: {e}")
        sys.exit(1)
