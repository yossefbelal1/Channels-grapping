import os
import sys
import json
import asyncio
import signal
import logging
import random
import time
import uuid
from datetime import datetime
from dotenv import load_dotenv
import redis
import psycopg2
from psycopg2.extras import RealDictCursor
from telethon import functions, errors
from telethon.tl.types import InputPeerUser, InputPeerChannel
from tg_manager import TelegramManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

load_dotenv()

# PostgreSQL credentials
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "leadhunter_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        cursor_factory=RealDictCursor
    )

async def send_telegram_message(client, peer, text, media_path=None):
    """
    Sub-dispatch function executed via tg_manager.execute_request
    """
    if media_path and os.path.exists(media_path):
        logging.info(f"Sending message with media: {media_path}")
        await client.send_message(peer, text, file=media_path)
    else:
        await client.send_message(peer, text)
    return True

async def main():
    logging.info("Starting Outreach Campaign Dispatcher Worker...")
    
    # Connect to Redis
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    try:
        redis_conn = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True
        )
        redis_conn.ping()
        logging.info("Successfully connected to Redis.")
    except Exception as e:
        logging.error(f"Failed to connect to Redis: {e}")
        sys.exit(1)

    # Retrieve preferred campaign session (default to primary)
    preferred_session = None
    try:
        with open("accounts.json", "r") as f:
            accounts = json.load(f)
            for acc in accounts:
                if acc.get("role") == "user_joiner" or acc.get("session_name") == "user_session":
                    preferred_session = acc.get("session_name")
                    break
    except Exception as e:
        logging.warning(f"Could not load preferred session from accounts.json: {e}")

    if not preferred_session:
        preferred_session = os.getenv("SESSION_NAME", "user_session")

    # Initialize Telegram Manager using the authorized session name
    tg_manager = TelegramManager(redis_conn, session_name=preferred_session, worker_type="campaign")
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

    logging.info(f"Campaign dispatcher preferred session set to: {preferred_session}")

    while not shutdown_event.is_set():
        conn = None
        cur = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()

            # Poll for a pending message attempt
            cur.execute("""
                SELECT cl.id as log_id, cl.campaign_id, cl.lead_id, c.message_text, c.media_path,
                       l.contact_username, l.channel_username, l.is_group
                FROM campaign_logs cl
                JOIN campaigns c ON cl.campaign_id = c.id
                JOIN leads l ON cl.lead_id = l.id
                WHERE cl.status = 'pending'
                ORDER BY c.created_at ASC, cl.sent_at ASC
                LIMIT 1
            """)
            pending_item = cur.fetchone()

            if not pending_item:
                # No pending campaign dispatches; sleep briefly before polling again
                cur.close()
                conn.close()
                await asyncio.sleep(10)
                continue

            log_id = pending_item['log_id']
            lead_id = pending_item['lead_id']
            message_text = pending_item['message_text']
            media_path = pending_item['media_path']
            contact_username = pending_item['contact_username']
            channel_username = pending_item['channel_username']

            # Resolve addressable peer username: strictly require contact_username for DMs
            target_username = contact_username
            if not target_username:
                logging.warning(f"No direct contact username found for lead ID: {lead_id}. Skipping channel board @{channel_username}.")
                cur.execute(
                    "UPDATE campaign_logs SET status = 'failed', error_message = %s, sent_at = %s WHERE id = %s",
                    ("No owner or admin contact username resolved for this channel", datetime.now(), log_id)
                )
                conn.commit()
                cur.close()
                conn.close()
                continue

            logging.info(f"Attempting outreach message delivery to @{target_username} (associated with channel @{channel_username})...")

            success = False
            error_message = None

            try:
                # Execute dispatch safely via tg_manager's rotation and rate-limit controls
                # 1. First obtain target input entity
                async def resolve_and_send(client):
                    peer = await client.get_input_entity(target_username)
                    return await send_telegram_message(client, peer, message_text, media_path)

                await tg_manager.execute_request(
                    preferred_session,
                    resolve_and_send,
                    shutdown_event=shutdown_event
                )
                success = True
            except errors.FloodWaitError as flood_err:
                error_message = f"Telegram rate limit: FloodWaitError ({flood_err.seconds}s)"
                logging.warning(f"Rate limit triggered for @{target_username}: {error_message}")
            except Exception as dispatch_err:
                error_message = str(dispatch_err)
                logging.error(f"Failed dispatch attempt to @{target_username}: {error_message}")

            if success:
                logging.info(f"Successfully sent message to @{target_username}!")
                cur.execute(
                    "UPDATE campaign_logs SET status = 'sent', sent_at = %s WHERE id = %s",
                    (datetime.now(), log_id)
                )
                cur.execute(
                    "UPDATE leads SET status = 'contacted', last_activity = %s WHERE id = %s",
                    (datetime.now(), lead_id)
                )
            else:
                logging.error(f"Outreach message delivery failed for @{target_username}: {error_message}")
                cur.execute(
                    "UPDATE campaign_logs SET status = 'failed', error_message = %s, sent_at = %s WHERE id = %s",
                    (error_message, datetime.now(), log_id)
                )

            conn.commit()
            cur.close()
            conn.close()

            # Enforce strict anti-ban sleep jitter (45 to 90 seconds)
            jitter_sleep = random.randint(45, 90)
            logging.info(f"Jitter sleep initiated. Resting for {jitter_sleep} seconds to mimic human interaction...")
            await asyncio.wait_for(shutdown_event.wait(), timeout=jitter_sleep)

        except asyncio.TimeoutError:
            pass
        except Exception as loop_err:
            logging.error(f"Error in Campaign worker main loop: {loop_err}")
            await asyncio.sleep(10)

    # Disconnect active Telegram session
    await tg_manager.disconnect_all()
    redis_conn.close()
    logging.info("Campaign worker has stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Process interrupted by user. Exiting.")
    except Exception as e:
        logging.critical(f"FATAL WORKER ERROR: {e}")
        sys.exit(1)
