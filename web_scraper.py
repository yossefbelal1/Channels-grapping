import os
import sys
import re
import json
import asyncio
import signal
import logging
import random
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import redis

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

# User Agent list to prevent blocks
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
]

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
    if 't.me/+' in link or 'telegram.me/+' in link:
        parts = link.split('/+')
        if len(parts) > 1:
            return 'private', parts[1].split('/')[0].split('?')[0]
            
    # Check for private invite links with 'joinchat' prefix
    private_joinchat_match = re.search(r'(?:t\.me|telegram\.me)/joinchat/([a-zA-Z0-9_-]+)', link, re.IGNORECASE)
    if private_joinchat_match:
        return 'private', private_joinchat_match.group(1).split('?')[0]
        
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

def scrape_search_engines(query: str, session: requests.Session) -> list:
    """
    Performs a search across Yahoo Search, DuckDuckGo Lite, and DuckDuckGo HTML,
    returning a deduplicated list of discovered t.me links.
    """
    discovered_links = []
    
    # 1. Query Yahoo Search (GET) - Extremely stable on cloud IPs and returns rich results
    url_yahoo = "https://search.yahoo.com/search"
    headers_yahoo = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    try:
        logging.info(f"Querying Yahoo Search for: '{query}'")
        response = session.get(url_yahoo, params={"p": query}, headers=headers_yahoo, timeout=15)
        if response.status_code == 200:
            from urllib.parse import unquote
            text_decoded = unquote(response.text)
            matches = TELEGRAM_LINK_REGEX.findall(text_decoded)
            discovered_links.extend(matches)
            logging.info(f"Yahoo Search successfully found {len(matches)} links.")
        else:
            logging.warning(f"Yahoo Search returned status code: {response.status_code}")
    except Exception as e:
        logging.error(f"Error querying Yahoo Search for query '{query}': {e}")
        
    # 2. Query DuckDuckGo Lite (POST) - High yield text interface
    url_lite = "https://lite.duckduckgo.com/lite/"
    headers_lite = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://lite.duckduckgo.com/"
    }
    try:
        logging.info(f"Querying DuckDuckGo Lite for: '{query}'")
        response = session.post(url_lite, data={"q": query}, headers=headers_lite, timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            for link_tag in soup.find_all("a", href=True):
                href = link_tag["href"]
                if "uddg=" in href:
                    from urllib.parse import urlparse, parse_qs, unquote
                    try:
                        parsed = urlparse(href)
                        params = parse_qs(parsed.query)
                        if "uddg" in params:
                            href = params["uddg"][0]
                    except Exception:
                        pass
                if "t.me/" in href or "telegram.me/" in href:
                    discovered_links.append(href)
            
            for td in soup.find_all("td", class_="result-snippet"):
                matches = TELEGRAM_LINK_REGEX.findall(td.get_text())
                discovered_links.extend(matches)
                
            matches = TELEGRAM_LINK_REGEX.findall(soup.get_text())
            discovered_links.extend(matches)
            logging.info(f"DuckDuckGo Lite finished querying.")
    except Exception as e:
        logging.error(f"Error querying DuckDuckGo Lite: {e}")

    # Deduplicate and clean URLs
    cleaned = []
    from urllib.parse import unquote
    for link in discovered_links:
        link = unquote(link)
        cleaned.append(link)
        
    return list(set(cleaned))


def scrape_google(query: str, session: requests.Session) -> list:
    """
    Searches Google Search.
    Fails over to DuckDuckGo Lite and Yahoo if blocked or challenge detected.
    """
    url = "https://www.google.com/search"
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    }
    discovered_links = []
    try:
        logging.info(f"Querying Google Search for: '{query}'")
        response = session.get(url, params={"q": query, "gbv": "1"}, headers=headers, timeout=15)
        
        # Check for CAPTCHA/Blocks/Consent screens
        if (response.status_code == 429 
            or "detected unusual traffic" in response.text 
            or "httpservice/retry/enablejs" in response.text
            or "consent.google" in response.text):
            logging.warning("Google Search blocked the query (challenge/CAPTCHA/Consent page). Failing over to DuckDuckGo/Yahoo...")
            return scrape_search_engines(query, session)
            
        if response.status_code == 200:
            # Find direct links
            matches = TELEGRAM_LINK_REGEX.findall(response.text)
            discovered_links.extend(matches)
            
            # Extract from Google redirects (/url?q=...)
            from urllib.parse import unquote
            redirects = re.findall(r'/url\?q=([^&"]+)', response.text)
            for r in redirects:
                decoded = unquote(r)
                if "t.me/" in decoded or "telegram.me/" in decoded:
                    discovered_links.append(decoded)
            
            logging.info(f"Google Search successfully retrieved results.")
        else:
            logging.warning(f"Google Search returned status code: {response.status_code}. Failing over...")
            return scrape_search_engines(query, session)
            
    except Exception as e:
        logging.error(f"Error querying Google Search: {e}. Failing over...")
        return scrape_search_engines(query, session)
        
    # Fail over to DDG/Yahoo if we found 0 links (Google returned a silent consent page or no results)
    if not discovered_links:
        logging.warning("Google Search returned 0 links (possible silent cookie consent block). Failing over to DuckDuckGo/Yahoo...")
        return scrape_search_engines(query, session)
        
    return list(set(discovered_links))


def scrape_youtube(query: str, session: requests.Session) -> list:
    """
    Searches YouTube, extracts video IDs from ytInitialData,
    fetches watch pages, and parses video descriptions for t.me links.
    """
    url = "https://www.youtube.com/results"
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.5"
    }
    discovered_links = []
    try:
        logging.info(f"Querying YouTube Search for: '{query}'")
        response = session.get(url, params={"search_query": query}, headers=headers, timeout=15)
        if response.status_code != 200:
            logging.warning(f"YouTube search returned status code: {response.status_code}")
            return []
            
        pattern = r"var ytInitialData\s*=\s*({.+?});"
        match = re.search(pattern, response.text)
        if not match:
            logging.warning("ytInitialData not found in YouTube search results.")
            return []
            
        data = json.loads(match.group(1))
        video_ids = []
        
        def traverse(node):
            if isinstance(node, dict):
                if "videoRenderer" in node:
                    vr = node["videoRenderer"]
                    vid = vr.get("videoId")
                    if vid:
                        video_ids.append(vid)
                for k, v in node.items():
                    traverse(v)
            elif isinstance(node, list):
                for item in node:
                    traverse(item)
                    
        traverse(data)
        video_ids = list(set(video_ids))
        logging.info(f"YouTube search returned {len(video_ids)} videos. Fetching descriptions...")
        
        # Limit to first 8 videos to avoid heavy rate limits
        for vid in video_ids[:8]:
            watch_url = f"https://www.youtube.com/watch?v={vid}"
            try:
                # Add a small delay between requests to prevent YouTube rate limiting
                import time
                time.sleep(random.uniform(1.5, 3.0))
                
                resp = session.get(watch_url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    # Broad check in page source
                    matches = TELEGRAM_LINK_REGEX.findall(resp.text)
                    discovered_links.extend(matches)
                    
                    # Target player response shortDescription
                    match_player = re.search(r"ytInitialPlayerResponse\s*=\s*({.+?});", resp.text)
                    if match_player:
                        player_data = json.loads(match_player.group(1))
                        video_details = player_data.get("videoDetails", {})
                        short_desc = video_details.get("shortDescription", "")
                        desc_links = TELEGRAM_LINK_REGEX.findall(short_desc)
                        discovered_links.extend(desc_links)
            except Exception as e:
                logging.error(f"Error fetching YouTube watch page {watch_url}: {e}")
                
    except Exception as e:
        logging.error(f"Error querying YouTube for '{query}': {e}")
        
    return list(set(discovered_links))


async def run_scraper_cycle(redis_conn: redis.Redis, shutdown_event: asyncio.Event):
    """
    Executes a search cycle over all predefined queries.
    """
    logging.info("Starting external web scraping cycle...")
    
    # 1. Search Engine Queries (site:t.me and direct directory indexing) - Focused on Arabic keywords only
    search_queries = [
        'site:t.me "فوركس"',
        'site:t.me "توصيات فوركس"',
        'site:t.me "XAUUSD عربي"',
        'site:t.me "توصيات الذهب"',
        'site:t.me "توصية"',
        'site:t.me "توصيات"',
        'site:t.me "صفقة"',
        'site:t.me "buy" "sell"',
        'site:t.me "شراء" "بيع"',
        'site:t.me "ضربت هدف"',
        'site:t.me "ضربت استوب"',
        'site:t.me "نتائج القناة الخاصة"',
        'site:t.me "كسر سعر"',
        'site:t.me "الذهب"',
        'site:t.me "تداول"',
        'site:t.me "منزل التحليل"',
        'site:t.me "تحليل الذهب"',
        'site:t.me "تداول العملات"',
        'site:t.me "تعليم فوركس"',
        'site:t.me "SMC فوركس"',
        'site:t.me "ICT توصيات"',
        'site:facebook.com "t.me/" "فوركس"',
        'site:facebook.com "t.me/" "توصيات"',
        'site:facebook.com "t.me/" "صفقة"',
        'site:facebook.com "t.me/" "تداول"',
        'site:x.com "t.me/" "فوركس"',
        'site:x.com "t.me/" "توصيات"',
        'site:x.com "t.me/" "صفقة"',
        'site:x.com "t.me/" "تداول"',
        'site:tiktok.com "t.me/" "فوركس"',
        'site:tiktok.com "t.me/" "توصيات"',
        'site:tiktok.com "t.me/" "صفقة"',
        'site:instagram.com "t.me/" "فوركس"',
        'site:instagram.com "t.me/" "توصيات"',
        'site:instagram.com "t.me/" "صفقة"',
        '"أفضل قنوات تليجرام توصيات فوركس"',
        '"قنوات تليجرام فوركس"',
        '"قنوات تليجرام توصيات الذهب"'
    ]
    
    # 2. YouTube Search Queries - Focused on Arabic keywords only
    youtube_queries = [
        'تعليم فوركس للمبتدئين',
        'توصيات فوركس مجانية',
        'توصيات الذهب تليجرام',
        'تداول العملات للمبتدئين',
        'تحليل الذهب اليومي',
        'تداول الذهب مباشر',
        'تعلم التداول من الصفر',
        'شرح SMC التداول',
        'شرح ICT فوركس',
        'إشارات فوركس تليجرام',
        'توصيات ذهب مباشر',
        'تحليل الذهب اليوم',
        'توصيات قنوات تليجرام صفقة هدف',
        'نتائج القناة الخاصة توصيات تليجرام',
        'تداول الذهب توصيات شراء بيع'
    ]
    
    session = requests.Session()
    new_channels = 0
    new_groups = 0
    
    # Process Google/Search engine queries
    random.shuffle(search_queries)
    for query in search_queries:
        if shutdown_event.is_set():
            break
            
        discovered_links = scrape_google(query, session)
        logging.info(f"Search query '{query}' returned {len(discovered_links)} potential links.")
        
        for raw_link in discovered_links:
            clean_link = raw_link.rstrip('.,;)!"\'/\\')
            clean_link = re.sub(r'[\(\)\[\]\{\}]', '', clean_link)
            if not clean_link:
                continue
                
            normalized = normalize_telegram_link(clean_link)
            link_type, identifier = parse_telegram_link(normalized)
            
            if not link_type or not identifier:
                continue
                
            if link_type == 'public':
                is_seen = redis_conn.sismember("seen_channels", normalized)
                if not is_seen:
                    redis_conn.sadd("seen_channels", normalized)
                    payload = json.dumps({
                        "link": normalized,
                        "source": query,
                        "method": "web_search",
                        "keyword": "external_scraper"
                    })
                    redis_conn.rpush("queue:normal", payload)
                    logging.info(f"[NEW CHANNEL] {normalized} routed to queue:normal")
                    new_channels += 1
            
            elif link_type == 'private':
                is_seen = redis_conn.sadd("scavenged_groups_set", normalized)
                if is_seen:
                    payload = json.dumps({
                        "link": normalized,
                        "source": query,
                        "method": "web_search",
                        "keyword": "external_scraper"
                    })
                    redis_conn.rpush("discovered_groups", payload)
                    logging.info(f"[NEW INVITE/GROUP] {normalized} routed to discovered_groups")
                    new_groups += 1
                    
        # Apply anti-ban jitter between queries
        delay = random.uniform(15.0, 30.0)
        logging.info(f"Sleeping for {delay:.2f}s before next query...")
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass

    # Process YouTube queries
    random.shuffle(youtube_queries)
    for query in youtube_queries:
        if shutdown_event.is_set():
            break
            
        discovered_links = scrape_youtube(query, session)
        logging.info(f"YouTube query '{query}' returned {len(discovered_links)} potential links.")
        
        for raw_link in discovered_links:
            clean_link = raw_link.rstrip('.,;)!"\'/\\')
            clean_link = re.sub(r'[\(\)\[\]\{\}]', '', clean_link)
            if not clean_link:
                continue
                
            normalized = normalize_telegram_link(clean_link)
            link_type, identifier = parse_telegram_link(normalized)
            
            if not link_type or not identifier:
                continue
                
            if link_type == 'public':
                is_seen = redis_conn.sismember("seen_channels", normalized)
                if not is_seen:
                    redis_conn.sadd("seen_channels", normalized)
                    payload = json.dumps({
                        "link": normalized,
                        "source": f"youtube:{query}",
                        "method": "youtube_search",
                        "keyword": "external_scraper"
                    })
                    # YouTube channels are high quality, route to high priority queue
                    redis_conn.rpush("queue:high", payload)
                    logging.info(f"[NEW CHANNEL - YT] {normalized} routed to queue:high")
                    new_channels += 1
            
            elif link_type == 'private':
                is_seen = redis_conn.sadd("scavenged_groups_set", normalized)
                if is_seen:
                    payload = json.dumps({
                        "link": normalized,
                        "source": f"youtube:{query}",
                        "method": "youtube_search",
                        "keyword": "external_scraper"
                    })
                    redis_conn.rpush("discovered_groups", payload)
                    logging.info(f"[NEW INVITE/GROUP - YT] {normalized} routed to discovered_groups")
                    new_groups += 1
                    
        # Apply anti-ban jitter between queries
        delay = random.uniform(15.0, 30.0)
        logging.info(f"Sleeping for {delay:.2f}s before next query...")
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass
            
    logging.info(f"Scraping cycle complete. Added {new_channels} new channels and {new_groups} new group invites.")


async def main():
    load_dotenv()
    
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    redis_db = int(os.getenv("REDIS_DB", 0))
    redis_password = os.getenv("REDIS_PASSWORD", None)
    
    interval = int(os.getenv("WEB_SCRAPER_INTERVAL_SECONDS", 21600)) # Default: 6 hours
    
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
        
    logging.info(f"Web Scraper service is active. Run interval: {interval}s.")
    
    while not shutdown_event.is_set():
        try:
            await run_scraper_cycle(redis_conn, shutdown_event)
        except Exception as e:
            logging.error(f"Unexpected error in scraper cycle: {e}", exc_info=True)
            
        if shutdown_event.is_set():
            break
            
        logging.info(f"Sleeping for {interval}s until next scheduled search...")
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
            
    redis_conn.close()
    logging.info("Worker D (The Web Scraper) has stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Process interrupted by user. Exiting.")
    except Exception as e:
        logging.critical(f"FATAL ERROR in web scraper: {e}")
        sys.exit(1)
