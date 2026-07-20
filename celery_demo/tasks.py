import os
import sys

# Allow importing analysis.py from the parent directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from celery import Celery
from data.analysis import run_financial_job, simulate_failure

# Both broker and result backend use local Redis, separated by db number
app = Celery(
    "celery_demo",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)


@app.task(name="celery_demo.calc_moving_averages")
def calc_moving_averages(prices, windows=(5, 20, 50)):
    """Moving average calculation task."""
    return run_financial_job(prices, tuple(windows))


@app.task(
    name="celery_demo.flaky_job",
    bind=True,
    autoretry_for=(RuntimeError,),
    retry_backoff=1,      # wait 1s before first retry, exponential backoff
    retry_backoff_max=5,
    max_retries=3,
)
def flaky_job(self, prices, fail=True):
    """Intentionally failing task for testing Celery's auto-retry mechanism.
    When fail=True, always raises -> retries 3 times then enters FAILURE state.
    """
    return simulate_failure(prices, fail=fail)
