"""
scripts/benchmark_pipeline.py — End-to-End Performance Benchmarking Suite

Measures actual system performance:
- Stage 1 validation throughput (ops/sec)
- Stage 2 13-dimension scoring throughput (ops/sec)
- Provenance candidate deduplication speed
- GrowthAnalyzer snapshot calculation latency
- Full pipeline simulation throughput across concurrency levels (1, 5, 10, 20 workers)
"""

import time
import sys
import os
import concurrent.futures
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.discovery.arabic_normalizer import calculate_arabic_letter_ratio, normalize_arabic_text
from app.discovery.taxonomy import classify_text_taxonomy
from app.scoring.engine import LeadScoringEngine
from app.scoring.growth_analyzer import GrowthAnalyzer
from app.discovery.provenance import ProvenanceManager


def benchmark_arabic_nlp(iterations=5000):
    sample_text = "قناة توصيات الذهب الرسمية، تحليلات فوركس XAUUSD يومية وسكالبينج مع إدارة رأس المال الاحترافية"
    start = time.perf_counter()
    for _ in range(iterations):
        normalize_arabic_text(sample_text)
        calculate_arabic_letter_ratio(sample_text)
        classify_text_taxonomy(sample_text)
    duration = time.perf_counter() - start
    ops_sec = iterations / duration
    print(f"[BENCHMARK] Arabic NLP & Taxonomy: {iterations} ops in {duration:.3f}s -> {ops_sec:,.0f} ops/sec")
    return ops_sec


def benchmark_scoring_engine(iterations=2000):
    sample_posts = [
        "صفقة شراء فوركس XAUUSD الدخول 2640 الهدف 2670 وقف الخسارة 2625",
        "تحديث السوق: اختراق مناطق العرض والطلب بنجاح ووصول الهدف الثاني +60 نقطة",
        "تحليل العملات الرقمية والذهب الأسبوعي برعاية وسيط مرخص ECN"
    ]
    start = time.perf_counter()
    for _ in range(iterations):
        LeadScoringEngine.evaluate_stage_1(
            title="نادي متداولي الذهب",
            description="تحليلات فنية وتوصيات فوركس",
            username="gold_trader_test",
            member_count=350
        )
        LeadScoringEngine.evaluate_stage_2(
            title="نادي متداولي الذهب",
            description="تحليلات فنية وتوصيات فوركس",
            recent_posts=sample_posts,
            member_count=350,
            has_contact=True,
            contact_types=["owner", "admin", "whatsapp"],
            posts_24h=3,
            posts_7d=15,
            posts_30d=40,
            last_post_at=datetime.now(timezone.utc)
        )
    duration = time.perf_counter() - start
    ops_sec = iterations / duration
    print(f"[BENCHMARK] 13-Dimension Scoring Engine: {iterations} evaluations in {duration:.3f}s -> {ops_sec:,.0f} eval/sec")
    return ops_sec


def benchmark_growth_analyzer(iterations=10000):
    t0 = datetime.now(timezone.utc)
    snaps = [
        {"member_count": 200, "recorded_at": t0 - timedelta(days=10)},
        {"member_count": 350, "recorded_at": t0 - timedelta(days=5)},
        {"member_count": 600, "recorded_at": t0}
    ]
    start = time.perf_counter()
    for _ in range(iterations):
        GrowthAnalyzer.calculate_growth_from_snapshots(snaps)
    duration = time.perf_counter() - start
    ops_sec = iterations / duration
    print(f"[BENCHMARK] Growth Analyzer: {iterations} snapshot calculations in {duration:.3f}s -> {ops_sec:,.0f} ops/sec")
    return ops_sec


def benchmark_concurrent_pipeline(concurrency_levels=[1, 5, 10, 20], total_jobs=1000):
    print("\n--- Concurrency Benchmark (Pipeline Throughput) ---")
    mock_redis = MagicMock()
    mock_redis.sadd.return_value = 1
    mock_db = MagicMock()

    for conc in concurrency_levels:
        jobs_per_worker = total_jobs // conc
        start = time.perf_counter()

        def worker_task(n):
            prov = ProvenanceManager(mock_redis, mock_db)
            for i in range(n):
                prov.record_candidate_discovery(f"channel_test_{i}", "global_search")
                LeadScoringEngine.evaluate_stage_1("Test", "Desc", f"chan_{i}", 200)

        with concurrent.futures.ThreadPoolExecutor(max_workers=conc) as executor:
            futures = [executor.submit(worker_task, jobs_per_worker) for _ in range(conc)]
            concurrent.futures.wait(futures)

        duration = time.perf_counter() - start
        rate = total_jobs / duration
        print(f"Concurrency {conc:2d} workers: {total_jobs} candidate cycles in {duration:.3f}s -> {rate:,.0f} candidates/sec")


if __name__ == "__main__":
    print("==================================================")
    print("Channels-grapping Performance Benchmark Suite")
    print("==================================================")
    benchmark_arabic_nlp()
    benchmark_scoring_engine()
    benchmark_growth_analyzer()
    benchmark_concurrent_pipeline()
    print("==================================================")
    print("Benchmark Completed Successfully.")
