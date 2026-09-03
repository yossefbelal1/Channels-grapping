"""
scripts/benchmark_phase1_search.py — Performance Benchmark for Phase 1 Telegram Search Discovery

Measures:
- Queries / minute
- Candidate extraction rate (results / minute)
- Unique channels / minute
- Duplicate detection & handling rate
- Average query parsing latency (ms)
"""

import time
import sys
import os
from unittest.mock import MagicMock
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.discovery.telegram_global_search import TelegramGlobalSearchEngine
from app.discovery.telegram_post_search import TelegramPostSearchEngine
from app.discovery.provenance import ProvenanceManager


def benchmark_search_extraction(iterations=1000):
    mock_redis = MagicMock()
    mock_db = MagicMock()
    mock_tg = MagicMock()

    engine = TelegramGlobalSearchEngine(mock_tg, mock_redis, mock_db)

    # Simulated search result payload with 20 messages & channels
    mock_channels = [
        MagicMock(id=1000 + i, username=f"trader_channel_{i}", broadcast=True, title=f"Trader {i}")
        for i in range(20)
    ]
    mock_messages = [
        MagicMock(
            id=5000 + i,
            chat=mock_channels[i % len(mock_channels)],
            text=f"XAUUSD BUY setup #{i} SL 2450 TP 2480",
            date=datetime.now(timezone.utc)
        )
        for i in range(20)
    ]
    mock_res = MagicMock(messages=mock_messages, chats=mock_channels)

    start = time.perf_counter()
    total_candidates = 0
    for _ in range(iterations):
        cands = engine.extract_channel_candidates(mock_res, "XAUUSD")
        total_candidates += len(cands)

    duration = time.perf_counter() - start
    queries_per_sec = iterations / duration
    queries_per_min = queries_per_sec * 60.0
    results_per_min = (total_candidates / duration) * 60.0
    avg_latency_ms = (duration / iterations) * 1000.0

    print(f"[BENCHMARK] Global Search Extraction ({iterations} queries, 20 msgs/query):")
    print(f"  - Queries/minute: {queries_per_min:,.0f}")
    print(f"  - Candidate results/minute: {results_per_min:,.0f}")
    print(f"  - Average latency per page parse: {avg_latency_ms:.3f} ms")

    return queries_per_min, results_per_min, avg_latency_ms


def benchmark_deduplication_speed(iterations=5000):
    mock_redis = MagicMock()
    # 80% new, 20% duplicate
    seen_set = set()
    def mock_sadd(key, val):
        if key == "seen_channels":
            # Simulate 20% duplicate rate
            if int(val.split('_')[-1]) % 5 == 0:
                return 0
            return 1
        return 1
    counts = {}
    def mock_incr(key):
        c = counts.get(key, 0) + 1
        counts[key] = c
        return c
    mock_redis.incr.side_effect = mock_incr
    mock_db = MagicMock()

    prov = ProvenanceManager(mock_redis, mock_db)

    start = time.perf_counter()
    new_count = 0
    dup_count = 0

    for i in range(iterations):
        is_new, _, _ = prov.record_candidate_discovery(f"forex_chan_{i}", "telegram_global_search")
        if is_new:
            new_count += 1
        else:
            dup_count += 1

    duration = time.perf_counter() - start
    ops_per_sec = iterations / duration
    unique_per_min = (new_count / duration) * 60.0
    dup_rate = (dup_count / iterations) * 100.0

    print(f"\n[BENCHMARK] Deduplication & Provenance Engine ({iterations} hits):")
    print(f"  - Processing rate: {ops_per_sec:,.0f} ops/sec")
    print(f"  - Unique channels/minute: {unique_per_min:,.0f}")
    print(f"  - Duplicate rate: {dup_rate:.1f}%")
    print(f"  - Total time: {duration:.3f} s")


if __name__ == "__main__":
    print("==================================================")
    print("Phase 1: Telegram Search Discovery Benchmark Suite")
    print("==================================================")
    benchmark_search_extraction()
    benchmark_deduplication_speed()
    print("==================================================")
    print("Benchmark Completed Successfully.")
