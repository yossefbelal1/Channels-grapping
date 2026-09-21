"""
scripts/spiderweb_and_enroll.py — Spiderweb Discovery & Direct Contact Auto-Enrollment

1. Runs SimilarChannelsCrawler from seed channels (@AlmaalFOREX, @SarhanIndicators, etc.).
2. Retrieves official Telegram recommendations using auxiliary research accounts (acc_12723433281, acc_14809564829, radar_session).
3. Fetches pinned messages (full_chat.pinned_msg_id) and extracts direct contacts (@admin, @analyst, support, WhatsApp).
4. Auto-enrolls all qualified leads with contacts into the active campaign with priority ranking.
"""

import os
import sys
import json
import asyncio
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.discovery.similar_channels_crawler import SimilarChannelsCrawler
from app.core.db import get_db_connection

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("spiderweb_enroll")


async def main():
    conn = get_db_connection()
    logger.info("Connected to PostgreSQL for Spiderweb Channel Ingestion.")

    # 1. Fetch top seeds from database or default list
    seeds = ["AlmaalFOREX", "SarhanIndicators", "fftrader", "sh0wmethemarket", "goldzone_trade", "kinforexs"]

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT channel_username 
                FROM leads 
                WHERE status = 'new' 
                  AND (lead_score >= 75 OR forex_intent_score >= 60)
                  AND channel_username ~ '^[a-zA-Z0-9_]{4,32}$'
                ORDER BY member_count DESC NULLS LAST
                LIMIT 10;
            """)
            db_seeds = [r['channel_username'] for r in cur.fetchall() if r.get('channel_username')]
            for s in db_seeds:
                if s not in seeds:
                    seeds.append(s)
    except Exception as e:
        logger.warning(f"Could not load seeds from DB: {e}")
    finally:
        conn.close()

    logger.info(f"Targeting {len(seeds)} Seed Channels for Spiderweb Expansion: {seeds[:8]}...")

    crawler = SimilarChannelsCrawler()
    stats = await crawler.spiderweb_crawl(seed_usernames=seeds, max_depth=1)

    print("\n" + "=" * 60)
    print("           SPIDERWEB RECOMMENDATIONS SUMMARY            ")
    print("=" * 60)
    print(f"Seeds Crawled:                   {len(seeds)}")
    print(f"Channels Inspected:              {stats['inspected_channels']}")
    print(f"Pinned Messages Analyzed:        {stats['pinned_messages_found']}")
    print(f"Direct Contacts Extracted:       {stats['contacts_extracted']}")
    print(f"Similar Channels Discovered:     {stats['similar_channels_discovered']}")
    print(f"Auto-Enrolled into Campaign:     {stats['campaign_auto_enrolled']}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
