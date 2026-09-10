"""Shared helpers for extractors that hit a flaky external source."""

from __future__ import annotations

import logging

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger("etl_pipeline.extract")


def with_retry(exceptions: tuple[type[Exception], ...], max_attempts: int = 5):
    """Decorator factory applying the pipeline's standard retry policy.

    Any extractor talking to a real, occasionally-flaky API can wrap its
    fetch method with this instead of rolling its own retry loop.
    """
    return retry(
        retry=retry_if_exception_type(exceptions),
        wait=wait_exponential_jitter(initial=0.5, max=10),
        stop=stop_after_attempt(max_attempts),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
