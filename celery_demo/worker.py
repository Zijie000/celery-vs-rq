"""
Launch a Celery worker.

Usage (from the celery_demo/ directory):
    celery -A tasks worker --loglevel=info --concurrency=4

This file serves as documentation and can also be used to start a worker
as a subprocess for concurrent benchmarking (see run_test.py for details).
"""
import subprocess
import sys

if __name__ == "__main__":
    concurrency = sys.argv[1] if len(sys.argv) > 1 else "4"
    subprocess.run(
        ["celery", "-A", "tasks", "worker", "--loglevel=info", f"--concurrency={concurrency}"],
        cwd=__file__.rsplit("/", 1)[0],
    )
