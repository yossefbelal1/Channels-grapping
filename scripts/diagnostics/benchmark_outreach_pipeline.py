"""
Benchmark script for the outreach pipeline.

Measures:
- Risk scoring latency
- Eligibility check latency
- Message validation latency
- Queue enqueue/dequeue throughput
- Adaptive throttle computation latency

Usage:
    python scripts/diagnostics/benchmark_outreach_pipeline.py
"""

import sys
import time
import statistics
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from unittest.mock import MagicMock


def benchmark_function(func, args=(), kwargs=None, iterations=1000):
    """Benchmark a function call and return timing stats."""
    kwargs = kwargs or {}
    times = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        func(*args, **kwargs)
        end = time.perf_counter_ns()
        times.append((end - start) / 1_000_000)  # Convert to ms

    return {
        'iterations': iterations,
        'min_ms': round(min(times), 3),
        'max_ms': round(max(times), 3),
        'mean_ms': round(statistics.mean(times), 3),
        'median_ms': round(statistics.median(times), 3),
        'p95_ms': round(sorted(times)[int(0.95 * len(times))], 3),
        'p99_ms': round(sorted(times)[int(0.99 * len(times))], 3),
        'ops_per_sec': round(1000 / statistics.mean(times)) if statistics.mean(times) > 0 else 0,
    }


def print_result(name, result):
    """Print benchmark result in a formatted way."""
    print(f"\n{'=' * 60}")
    print(f"  {name}")
    print(f"{'=' * 60}")
    print(f"  Iterations:  {result['iterations']}")
    print(f"  Min:         {result['min_ms']} ms")
    print(f"  Max:         {result['max_ms']} ms")
    print(f"  Mean:        {result['mean_ms']} ms")
    print(f"  Median:      {result['median_ms']} ms")
    print(f"  P95:         {result['p95_ms']} ms")
    print(f"  P99:         {result['p99_ms']} ms")
    print(f"  Throughput:  {result['ops_per_sec']} ops/sec")


def main():
    print("Outreach Pipeline Benchmark")
    print("=" * 60)

    # Setup mocks for benchmarking computation speed (no I/O)
    mock_redis = MagicMock()
    mock_redis.get.return_value = "85"
    mock_redis.exists.return_value = False
    mock_redis.llen.return_value = 10
    mock_redis.pipeline.return_value = MagicMock()

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {'count': 0, 'total_sends': 100, 'total_failures': 5,
                                          'health_score': 85, 'lead_score': 75, 'state': 'HEALTHY'}
    mock_cursor.fetchall.return_value = []

    # 1. Risk Scoring
    from app.outreach.risk_scorer import calculate_risk_score
    result = benchmark_function(
        calculate_risk_score,
        args=(mock_redis, mock_cursor, 'test-lead-id', 'test-session', 'test-campaign'),
        iterations=5000
    )
    print_result("Risk Scoring (calculate_risk_score)", result)

    # 2. Eligibility Check
    from app.outreach.eligibility import check_eligibility
    result = benchmark_function(
        check_eligibility,
        args=(mock_redis, mock_cursor, 'test-lead-id', 'test-campaign', 'test_username'),
        iterations=5000
    )
    print_result("Eligibility Check (check_eligibility)", result)

    # 3. Message Validation
    from app.outreach.message_validator import validate_message
    test_message = "مرحباً! نحن نقدم خدمات تداول الفوركس والعملات الرقمية. للمزيد من المعلومات تواصل معنا."
    result = benchmark_function(
        validate_message,
        args=(test_message,),
        iterations=10000
    )
    print_result("Message Validation (validate_message)", result)

    # 4. Risk Level Classification
    from app.outreach.risk_scorer import classify_risk_level
    result = benchmark_function(
        classify_risk_level,
        args=(42,),
        iterations=50000
    )
    print_result("Risk Classification (classify_risk_level)", result)

    # 5. Queue Enqueue
    from app.outreach.queue_manager import OutreachQueueManager
    qm = OutreachQueueManager(mock_redis)
    result = benchmark_function(
        qm.enqueue,
        args=('lead-id', 'campaign-id', 'LOW'),
        iterations=5000
    )
    print_result("Queue Enqueue (OutreachQueueManager.enqueue)", result)

    # 6. Adaptive Throttle
    from app.outreach.adaptive_throttle import AdaptiveThrottle
    throttle = AdaptiveThrottle(mock_redis, 'test-session')
    result = benchmark_function(
        throttle.get_next_delay,
        iterations=5000
    )
    print_result("Adaptive Throttle (get_next_delay)", result)

    # 7. Circuit Breaker Check
    from app.outreach.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker(mock_redis)
    mock_redis.exists.return_value = False
    result = benchmark_function(
        cb.check_account_circuit,
        args=('test-session',),
        iterations=10000
    )
    print_result("Circuit Breaker Check (check_account_circuit)", result)

    # 8. Emergency Check
    from app.outreach.emergency import is_outreach_enabled
    result = benchmark_function(
        is_outreach_enabled,
        args=(mock_redis,),
        iterations=10000
    )
    print_result("Emergency Check (is_outreach_enabled)", result)

    # 9. Backpressure Check
    from app.outreach.backpressure import BackpressureManager
    bp = BackpressureManager(mock_redis)
    result = benchmark_function(
        bp.get_outreach_level,
        iterations=5000
    )
    print_result("Backpressure Level Check (get_outreach_level)", result)

    print(f"\n{'=' * 60}")
    print("  Benchmark Complete")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
