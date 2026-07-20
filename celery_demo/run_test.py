"""
Submit Celery tasks and measure timing. Start the worker in another terminal first:

    cd celery_demo
    celery -A tasks worker --loglevel=info --concurrency=4

Then run:
    python run_test.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from celery import group
from data.generate_dummy_prices import generate_prices
from tasks import calc_moving_averages, flaky_job

N_POINTS = 5000
BATCH_SIZE = 50


def test_single_task():
    prices = generate_prices(N_POINTS, seed=1)
    start = time.perf_counter()
    async_result = calc_moving_averages.delay(prices, [5, 20, 50])
    result = async_result.get(timeout=30)   # block until result is ready
    wall_clock = time.perf_counter() - start
    print(f"[Single task] submit->result wall time: {wall_clock:.4f}s | task compute time: {result['elapsed_seconds']}s")
    return wall_clock


def test_batch_tasks():
    """Submit BATCH_SIZE tasks concurrently via group and measure total throughput time."""
    prices_list = [generate_prices(N_POINTS, seed=i) for i in range(BATCH_SIZE)]
    job = group(calc_moving_averages.s(p, [5, 20, 50]) for p in prices_list)

    start = time.perf_counter()
    result_group = job.apply_async()
    results = result_group.get(timeout=60)
    wall_clock = time.perf_counter() - start

    print(f"[Batch {BATCH_SIZE} tasks] total: {wall_clock:.4f}s | "
          f"avg per task: {wall_clock / BATCH_SIZE:.4f}s | succeeded: {len(results)}/{BATCH_SIZE}")
    return wall_clock


def test_retry_and_failure():
    """Reliability test: submit a task that always fails and observe auto-retry behavior."""
    prices = generate_prices(100, seed=2)
    async_result = flaky_job.delay(prices, True)
    try:
        async_result.get(timeout=30)
    except Exception as e:
        print(f"[Retry test] Task failed as expected (gave up after 3 retries): {type(e).__name__}: {e}")
        print(f"[Retry test] Final task state: {async_result.state}")


if __name__ == "__main__":
    print("=== Celery test start ===")
    print(f"(Make sure the worker is running in another terminal: celery -A tasks worker --loglevel=info)\n")
    test_single_task()
    test_batch_tasks()
    test_retry_and_failure()
    print("=== Celery test complete ===")
