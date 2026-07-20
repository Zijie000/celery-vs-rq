import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data.analysis import run_financial_job, simulate_failure


def calc_moving_averages(prices, windows=(5, 20, 50)):
    """Moving average calculation task (identical logic to celery_demo for a fair comparison)."""
    return run_financial_job(prices, tuple(windows))


def flaky_job(prices, fail=True):
    """Intentionally failing task for use with RQ's Retry mechanism."""
    return simulate_failure(prices, fail=fail)
