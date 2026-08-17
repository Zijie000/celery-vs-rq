"""A simulated flaky financial API used for exercising the retry client.

Not a real API client — it's a stand-in that fails randomly so the retry
logic in `client.py` has something realistic to retry against.
"""

from __future__ import annotations

import random
import time


class RateLimitError(Exception):
    """Raised when the API reports HTTP 429 (too many requests)."""


class ServiceUnavailableError(Exception):
    """Raised when the API reports HTTP 503 (temporarily down)."""


class TimeoutError(Exception):
    """Raised when the request takes too long to respond."""


TRANSIENT_ERRORS = (RateLimitError, ServiceUnavailableError, TimeoutError)


class FlakyFinancialAPI:
    """Simulates a financial quotes API with a configurable failure rate.

    Each call to `get_quote` independently fails with probability
    `failure_rate`, raising one of the transient errors above. Callers are
    expected to retry on these errors.
    """

    def __init__(self, failure_rate: float = 0.6, latency: float = 0.05, seed: int | None = None):
        self.failure_rate = failure_rate
        self.latency = latency
        self._rng = random.Random(seed)

    def get_quote(self, symbol: str) -> dict:
        time.sleep(self.latency)

        if self._rng.random() < self.failure_rate:
            error = self._rng.choice(TRANSIENT_ERRORS)
            raise error(f"{error.__name__} while fetching quote for {symbol}")

        price = round(self._rng.uniform(50, 500), 2)
        return {"symbol": symbol, "price": price, "currency": "USD"}
