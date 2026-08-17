"""Financial API client with retry + exponential backoff.

Wraps calls to a flaky financial API (see `flaky_api.py`) using `tenacity`
to retry on transient errors, with exponential backoff, jitter, a retry
cap, and logging of each attempt and the final outcome.
"""

from __future__ import annotations

import logging

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
    before_sleep_log,
)

from flaky_api import FlakyFinancialAPI, TRANSIENT_ERRORS

logger = logging.getLogger("financial_api_client")


class QuoteFetchError(Exception):
    """Raised when all retry attempts to fetch a quote are exhausted."""


def _log_final_failure(retry_state):
    exc = retry_state.outcome.exception()
    symbol = retry_state.args[0] if retry_state.args else retry_state.kwargs.get("symbol")
    logger.error(
        "Giving up fetching quote for %s after %d attempts: %s",
        symbol,
        retry_state.attempt_number,
        exc,
    )
    raise QuoteFetchError(
        f"Failed to fetch quote after {retry_state.attempt_number} attempts: {exc}"
    ) from exc


class FinancialAPIClient:
    """Client that fetches quotes with automatic retry on transient failures."""

    def __init__(
        self,
        api: FlakyFinancialAPI,
        max_attempts: int = 5,
        initial_wait: float = 0.5,
        max_wait: float = 10,
    ):
        self.api = api
        self._retrying_get_quote = retry(
            retry=retry_if_exception_type(TRANSIENT_ERRORS),
            wait=wait_exponential_jitter(initial=initial_wait, max=max_wait, jitter=0.5),
            stop=stop_after_attempt(max_attempts),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            retry_error_callback=_log_final_failure,
            reraise=False,
        )(self._fetch_quote)

    def get_quote(self, symbol: str) -> dict:
        return self._retrying_get_quote(symbol)

    def _fetch_quote(self, symbol: str) -> dict:
        result = self.api.get_quote(symbol)
        logger.info("Fetched quote for %s: $%s", symbol, result["price"])
        return result
