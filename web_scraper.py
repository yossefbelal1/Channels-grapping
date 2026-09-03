"""
web_scraper.py — Production Pluggable Web & Directory Scraper (Worker E)

Discovers public Arabic Forex / Trading channels from search engines,
directories, and blogs, pushing deduplicated leads to Redis validation queues.
"""

import os
import sys
import json
import asyncio
import signal
import logging
import random
from dotenv import load_dotenv
import redis

# Discovery Modules
from app.discovery.taxonomy import get_all_keywords, KEYWORD_TAXONOMY
from app.discovery.arabic_normalizer import generate_query_variants
from app.discovery.provenance import ProvenanceManager
from app.web_discovery.engines import WebDiscoveryEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [WEB-SCRAPER] [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)


async def run_web_scraping_cycle(
    engine: WebDiscoveryEngine,
    redis_conn: redis.Redis,
    provenance_mgr: ProvenanceManager,
    shutdown_event: asyncio.Event
):
    """
    Runs a complete web discovery pass across all taxonomy queries.
    """
    logging.info("Starting Web Discovery cycle...")
    all_keywords = get_all_keywords()
    random.shuffle(all_keywords)

    total_discovered = 0

    for kw in all_keywords[:25]: # Process 25 keywords per cycle
        if shutdown_event.is_set():
            break

        # Check queue backpressure
        try:
            q_len = redis_conn.llen("queue:normal") + redis_conn.llen("queue:high")
            while q_len >= 1000 and not shutdown_event.is_set():
                logging.warning(f"Backpressure active ({q_len} queued). Pausing web discovery...")
                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=30)
                except asyncio.TimeoutError:
                    pass
                q_len = redis_conn.llen("queue:normal") + redis_conn.llen("queue:high")
        except Exception:
            pass

        logging.info(f"Scraping web for: '{kw}'...")
        links = engine.discover_channels_for_query(kw)

        for link in links:
            is_new, count, sources = provenance_mgr.record_candidate_discovery(
                username_or_link=link,
                source_type="web",
                keyword=kw
            )

            if is_new:
                payload = json.dumps({
                    "link": link,
                    "source": f"web_search:{kw}",
                    "method": "web",
                    "keyword": kw,
                    "discovered_count": count,
                    "sources": sources
                })
                redis_conn.rpush("queue:normal", payload)
                total_discovered += 1
                logging.info(f"Web Discovered: {link} (Query: '{kw}')")

        # Anti-scraping jitter between search queries
        delay = random.uniform(5.0, 12.0)
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass

    logging.info(f"Web discovery cycle finished. Found and queued {total_discovered} new candidates.")


async def main():
    load_dotenv()

    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    redis_db = int(os.getenv("REDIS_DB", 0))
    redis_password = os.getenv("REDIS_PASSWORD", None)

    interval = int(os.getenv("WEB_SCRAPER_INTERVAL_SECONDS", 7200)) # 2 hours default

    try:
        redis_conn = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True
        )
        redis_conn.ping()
        logging.info("Redis connected successfully.")
    except Exception as e:
        logging.error(f"Failed to connect to Redis: {e}")
        sys.exit(1)

    engine = WebDiscoveryEngine()
    provenance_mgr = ProvenanceManager(redis_conn)

    shutdown_event = asyncio.Event()

    def stop():
        logging.info("Web scraper shutdown initiated.")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop)
    except NotImplementedError:
        pass

    logging.info("Web Scraper Worker is active.")

    while not shutdown_event.is_set():
        try:
            await run_web_scraping_cycle(engine, redis_conn, provenance_mgr, shutdown_event)
        except Exception as e:
            logging.error(f"Error in web scraper cycle: {e}", exc_info=True)

        logging.info(f"Sleeping for {interval}s until next web scraping cycle...")
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass

    redis_conn.close()
    logging.info("Web scraper worker stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Interrupted by user.")
    except Exception as e:
        logging.critical(f"FATAL ERROR: {e}")
        sys.exit(1)
