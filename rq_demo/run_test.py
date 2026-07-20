"""
Submit RQ tasks and measure timing. Start one or more workers in another terminal first:

    cd rq_demo
    rq worker -u redis://localhost:6379/2 --with-scheduler financial_jobs

Note: --with-scheduler is required; without it, delayed retries in
test_retry_and_failure() will never be re-queued and will time out.
See worker.py for details.

Then run:
    python run_test.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from redis import Redis
from rq import Queue, Retry
from rq.job import JobStatus

from data.generate_dummy_prices import generate_prices
from tasks import calc_moving_averages, flaky_job

redis_conn = Redis.from_url("redis://localhost:6379/2")
queue = Queue("financial_jobs", connection=redis_conn)

N_POINTS = 5000
BATCH_SIZE = 50
POLL_INTERVAL = 0.05


def wait_for_job(job, timeout=30):
    """RQ has no blocking .get() like Celery, so we poll status manually."""
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        job.refresh()
        if job.get_status() in (JobStatus.FINISHED, JobStatus.FAILED):
            return job
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"Job {job.id} timed out")


def wait_for_jobs(jobs, timeout=60):
    deadline = time.perf_counter() + timeout
    pending = set(j.id for j in jobs)
    job_map = {j.id: j for j in jobs}
    while pending and time.perf_counter() < deadline:
        done_now = set()
        for jid in pending:
            job_map[jid].refresh()
            if job_map[jid].get_status() in (JobStatus.FINISHED, JobStatus.FAILED):
                done_now.add(jid)
        pending -= done_now
        if pending:
            time.sleep(POLL_INTERVAL)
    if pending:
        raise TimeoutError(f"{len(pending)} jobs did not complete before timeout")
    return jobs


def test_single_task():
    prices = generate_prices(N_POINTS, seed=1)
    start = time.perf_counter()
    job = queue.enqueue(calc_moving_averages, prices, [5, 20, 50])
    wait_for_job(job)
    wall_clock = time.perf_counter() - start
    result = job.return_value()
    print(f"[Single task] submit->result wall time: {wall_clock:.4f}s | task compute time: {result['elapsed_seconds']}s")
    return wall_clock


def test_batch_tasks():
    prices_list = [generate_prices(N_POINTS, seed=i) for i in range(BATCH_SIZE)]

    start = time.perf_counter()
    jobs = [queue.enqueue(calc_moving_averages, p, [5, 20, 50]) for p in prices_list]
    wait_for_jobs(jobs)
    wall_clock = time.perf_counter() - start

    success = sum(1 for j in jobs if j.get_status() == JobStatus.FINISHED)
    print(f"[Batch {BATCH_SIZE} tasks] total: {wall_clock:.4f}s | "
          f"avg per task: {wall_clock / BATCH_SIZE:.4f}s | succeeded: {success}/{BATCH_SIZE}")
    return wall_clock


def test_retry_and_failure():
    """RQ retry is configured via Retry(max=N, interval=[...])."""
    prices = generate_prices(100, seed=2)
    job = queue.enqueue(
        flaky_job, prices, True,
        retry=Retry(max=3, interval=[1, 2, 4]),
    )
    wait_for_job(job, timeout=30)
    print(f"[Retry test] Final task state: {job.get_status()}")
    if job.get_status() == JobStatus.FAILED:
        print(f"[Retry test] Task failed as expected (gave up after 3 retries)")


if __name__ == "__main__":
    print("=== RQ test start ===")
    print("(Make sure the worker is running in another terminal: rq worker -u redis://localhost:6379/2 financial_jobs)\n")
    test_single_task()
    test_batch_tasks()
    test_retry_and_failure()
    print("=== RQ test complete ===")
