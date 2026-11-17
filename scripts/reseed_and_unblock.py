#!/usr/bin/env python3
"""
scripts/reseed_and_unblock.py

Automated Recovery & Seeding Script:
1. Unblocks Outreach Engine in Redis (deletes emergency stop, clears limits).
2. Clears stale session locks and search checkpoints.
3. Reclaims any stuck 'processing' records in campaign_logs back to 'approved'.
4. Seeds top qualified Arabic Forex channels from PostgreSQL into Redis recommendations:queue
   so worker_graph_expander spiderweb crawls them immediately.
"""

import os
import sys
import json
import logging
import redis
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "leadhunter_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "leadhunter_pass")


def main():
    # ── 1. Connect to Redis ──────────────────────────────────────────────
    logging.info(f"Connecting to Redis at {REDIS_HOST}:{REDIS_PORT}...")
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    r.ping()
    logging.info("Redis connected successfully.")

    # ── 2. Unblock Outreach Engine ───────────────────────────────────────
    deleted_stop = r.delete("outreach:emergency_stop")
    r.set("outreach:global:enabled", 1)
    r.delete("health:spiderweb_session:rate_limited_until")
    r.delete("health:user_session:dm_rate_limited_until")
    logging.info(f"Outreach unblocked: emergency_stop deleted={deleted_stop}, outreach:global:enabled=1")

    # Clear stale session locks
    lock_keys = r.keys("lock:session:*")
    if lock_keys:
        r.delete(*lock_keys)
        logging.info(f"Deleted {len(lock_keys)} stale session locks: {lock_keys}")
    else:
        logging.info("No stale session locks found.")

    # Clear search checkpoints to allow fresh discoveries
    cp_keys = r.keys("checkpoint:telegram_global_search:*")
    if cp_keys:
        r.delete(*cp_keys)
        logging.info(f"Reset {len(cp_keys)} global search checkpoints for scraper refresh.")

    # ── 3. Connect to PostgreSQL ────────────────────────────────────────
    logging.info(f"Connecting to PostgreSQL at {DB_HOST}:{DB_PORT}/{DB_NAME}...")
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 3a. Reclaim stuck 'processing' rows
    cur.execute("UPDATE campaign_logs SET status = 'approved' WHERE status = 'processing';")
    reclaimed = cur.rowcount
    conn.commit()
    logging.info(f"Reclaimed {reclaimed} stuck 'processing' campaign_logs rows back to 'approved'.")

    # 3b. Check campaign_logs status counts
    cur.execute("SELECT status, count(*) AS cnt FROM campaign_logs GROUP BY status ORDER BY cnt DESC;")
    status_counts = cur.fetchall()
    logging.info("Campaign Logs Distribution:")
    for row in status_counts:
        logging.info(f"  - {row['status']}: {row['cnt']}")

    # 3c. Find top qualified Arabic Forex channels for spiderweb seeding
    cur.execute("""
        SELECT id, channel_username, title, lead_score
        FROM leads
        WHERE lead_score >= 60 AND channel_username IS NOT NULL AND length(channel_username) > 3
        ORDER BY lead_score DESC
        LIMIT 150;
    """)
    seeds = cur.fetchall()
    logging.info(f"Found {len(seeds)} high-score Arabic Forex seeds (lead_score >= 60).")

    # ── 4. Seed into Redis recommendations:queue ────────────────────────
    seeded_count = 0
    for s in seeds:
        uname = s['channel_username'].lstrip('@').strip()
        if not uname:
            continue
        payload = json.dumps({
            "username": uname,
            "channel_id": str(s['id']),
            "depth": 0,
            "tier": "Tier_A" if s['lead_score'] >= 80 else "Tier_B"
        })
        r.rpush("recommendations:queue", payload)
        seeded_count += 1

    logging.info(f"Successfully seeded {seeded_count} channels into Redis 'recommendations:queue'.")

    # ── 5. Telemetry & Queue Depths ─────────────────────────────────────
    q_high = r.llen("queue:high")
    q_normal = r.llen("queue:normal")
    q_critical = r.llen("queue:critical")
    q_recs = r.llen("recommendations:queue")
    outreach_high = r.llen("outreach:high")
    outreach_normal = r.llen("outreach:normal")

    logging.info("=== Current Queue Depths ===")
    logging.info(f"  - recommendations:queue : {q_recs}")
    logging.info(f"  - queue:high            : {q_high}")
    logging.info(f"  - queue:normal          : {q_normal}")
    logging.info(f"  - queue:critical        : {q_critical}")
    logging.info(f"  - outreach:high         : {outreach_high}")
    logging.info(f"  - outreach:normal       : {outreach_normal}")
    logging.info("Recovery and seeding completed successfully!")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
