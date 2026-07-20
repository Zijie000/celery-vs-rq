"""
Launch RQ workers.

Usage (from the rq_demo/ directory). Note: RQ's default worker is single-process
single-threaded, so concurrency requires multiple worker processes — unlike Celery,
which supports multiple subprocesses within one worker process:

    rq worker -u redis://localhost:6379/2 --with-scheduler financial_jobs

To simulate concurrency, open multiple terminals and run the command above in each
(or use this script to spawn N worker subprocesses at once).

[IMPORTANT GOTCHA] --with-scheduler is required!
If tasks use Retry(interval=[...]) for delayed retries, failed tasks are placed in
the "scheduled" registry to wait until their retry time. A plain `rq worker` does
not actively process this registry — you must pass --with-scheduler (or run a
separate `rq scheduler` process) so that due retries are periodically moved back
into the queue. Without this flag, retried tasks stay stuck in the scheduled state
and are never re-executed, causing them to silently "disappear" and the caller to
time out waiting. This was found via real testing; Celery does not have this issue
since its auto-retry is built into the worker and needs no extra process.
"""
import subprocess
import sys
import os

if __name__ == "__main__":
    n_workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    cwd = os.path.dirname(os.path.abspath(__file__))
    procs = []
    for _ in range(n_workers):
        p = subprocess.Popen(
            ["rq", "worker", "-u", "redis://localhost:6379/2", "--with-scheduler", "financial_jobs"],
            cwd=cwd,
        )
        procs.append(p)
    for p in procs:
        p.wait()
