"""
One-off script to trigger negative corpus harvesting and signal mining on the VPS.
"""
import os
import sys
import psycopg2
import redis
from app.learning.corpus_harvester import CorpusHarvester
from app.learning.pattern_miner import PatternMiner
from app.learning.signal_lifecycle import SignalLifecycle, SignalStatus
from app.learning.knowledge_model import KnowledgeModel

def main():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set")
        sys.exit(1)

    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

    conn = psycopg2.connect(db_url)
    print("Connected to PostgreSQL database.")

    # 1. Harvest negative corpus
    print("Harvesting negative corpus from rejected non-trading leads...")
    neg = CorpusHarvester.harvest_negative_corpus(conn, limit=100)
    print(f"Harvested and stored {len(neg)} negative channels in corpus_channels.")

    # 2. Load cached gold corpus
    pos = CorpusHarvester.load_cached_corpus(conn, "gold_admin")
    print(f"Loaded {len(pos)} Gold Admin channels from corpus_channels.")

    # 3. Mine contrastive patterns
    print("Mining contrastive patterns between Gold and Negative corpora...")
    mined = PatternMiner.mine_and_score(pos, neg)
    print(f"Mined {len(mined)} contrastive candidate signals.")

    # 4. Upsert into discovered_signals
    upserted_cnt = 0
    active_cnt = 0
    validated_cnt = 0
    candidate_cnt = 0
    observed_cnt = 0

    for sig in mined:
        res = SignalLifecycle.upsert_signal(
            conn,
            signal_type=sig["signal_type"],
            signal_value=sig["signal_value"],
            normalized_value=sig["normalized_value"],
            category=sig["category"],
            pos_support=sig["positive_support_count"],
            neg_penalty=sig["negative_penalty_count"],
            contrast_score=sig["contrast_score"],
            provenance=sig["provenance_sources"],
            evidence=sig["evidence_samples"]
        )
        if res:
            upserted_cnt += 1
            st = res.get("status")
            if st == SignalStatus.ACTIVE:
                active_cnt += 1
            elif st == SignalStatus.VALIDATED:
                validated_cnt += 1
            elif st == SignalStatus.CANDIDATE:
                candidate_cnt += 1
            elif st == SignalStatus.OBSERVED:
                observed_cnt += 1

    print(f"Signal lifecycle results:")
    print(f"  Total Persisted: {upserted_cnt}")
    print(f"  Active: {active_cnt}")
    print(f"  Validated: {validated_cnt}")
    print(f"  Candidate: {candidate_cnt}")
    print(f"  Observed: {observed_cnt}")

    # 5. Sync to Redis KnowledgeModel
    try:
        r = redis.from_url(redis_url)
        km = KnowledgeModel()
        if km.load_from_db(conn):
            km.sync_to_redis(r)
            print(f"Knowledge model synced to Redis: {len(km.active_keywords)} active keywords, {len(km.active_phrases)} active phrases, {len(km.active_symbols)} symbols, {len(km.candidate_phrases)} candidate phrases.")
    except Exception as e:
        print(f"Redis sync warning: {e}")

if __name__ == "__main__":
    main()
