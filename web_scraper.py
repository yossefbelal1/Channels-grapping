"""
web_scraper.py — Production Cross-Platform Unified Discovery Worker (Worker E)

Discovers public Arabic Forex / Trading channels, accounts, and communities
across Web, TikTok, Facebook, and Telegram, constructs the multi-edge cross-platform
graph, and routes newly discovered Telegram leads into the validation queues.
"""

import os
import sys
import json
import asyncio
import signal
import logging
from dotenv import load_dotenv
import redis
import psycopg2
from psycopg2.extras import RealDictCursor

# Core & Discovery Modules
from app.core.db import get_db_pool
from app.discovery.cross_platform_engine import CrossPlatformDiscoveryEngine
from app.discovery.query_generator import QueryGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [CROSS-DISCOVERY] [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)


async def main():
    load_dotenv()

    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    redis_db = int(os.getenv("REDIS_DB", 0))
    redis_password = os.getenv("REDIS_PASSWORD", None)

    db_host = os.getenv("DB_HOST", "localhost")
    db_port = int(os.getenv("DB_PORT", 5432))
    db_name = os.getenv("DB_NAME", "leadhunter_db")
    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD", "")

    interval = int(os.getenv("WEB_SCRAPER_INTERVAL_SECONDS", 1800))  # 30 minutes default

    # 1. Connect to Redis
    try:
        redis_conn = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True
        )
        redis_conn.ping()
        logging.info("Connected to Redis successfully.")
    except Exception as e:
        logging.error(f"Failed to connect to Redis: {e}")
        sys.exit(1)

    # 2. Connect to PostgreSQL
    db_conn = None
    try:
        db_conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            dbname=db_name,
            user=db_user,
            password=db_password,
            cursor_factory=RealDictCursor
        )
        logging.info("Connected to PostgreSQL successfully.")
    except Exception as e:
        logging.warning(f"PostgreSQL direct connection failed, attempting pool: {e}")
        try:
            pool = get_db_pool()
            db_conn = pool.getconn()
        except Exception as pool_err:
            logging.error(f"Failed to connect to PostgreSQL: {pool_err}")

    # 3. Initialize Cross-Platform Discovery Engine
    query_gen = QueryGenerator()
    engine = CrossPlatformDiscoveryEngine(
        redis_conn=redis_conn,
        db_conn=db_conn,
        query_generator=query_gen
    )

    shutdown_event = asyncio.Event()

    def stop():
        logging.info("Cross-platform discovery shutdown initiated.")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop)
    except NotImplementedError:
        pass

    logging.info("Cross-Platform Unified Discovery Worker is active.")

    while not shutdown_event.is_set():
        try:
            # Ensure DB connection is alive
            if db_conn and db_conn.closed:
                try:
                    db_conn = psycopg2.connect(
                        host=db_host, port=db_port, dbname=db_name,
                        user=db_user, password=db_password, cursor_factory=RealDictCursor
                    )
                    engine.db = db_conn
                    engine.graph_mgr.db = db_conn
                    engine.spider.db = db_conn
                except Exception:
                    pass

            await engine.run_discovery_cycle(shutdown_event)
        except Exception as e:
            logging.error(f"Error in cross-platform discovery cycle: {e}", exc_info=True)

        logging.info(f"Sleeping for {interval}s until next cross-platform discovery cycle...")
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass

    redis_conn.close()
    if db_conn and not db_conn.closed:
        db_conn.close()
    logging.info("Cross-platform discovery worker stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Interrupted by user.")
    except Exception as e:
        logging.critical(f"FATAL ERROR: {e}")
        sys.exit(1)
