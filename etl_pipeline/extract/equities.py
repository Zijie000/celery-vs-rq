"""Equity price extractor.

Stands in for a real equities market-data API (e.g. Alpha Vantage, IEX,
Polygon). It fails transiently at random like a real HTTP client would,
and recovers via the shared retry policy, so the demo exercises the same
resilience path a production extractor would need.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from ..core import Extractor, Record
from .base import with_retry


class TransientAPIError(Exception):
    """Simulated transient failure (rate limit / timeout / 5xx)."""


class EquityExtractor(Extractor):
    """Fetches a synthetic daily close price series for equity symbols."""

    def __init__(
        self,
        symbols: list[str],
        days: int = 30,
        failure_rate: float = 0.15,
        seed: int | None = None,
    ):
        self.symbols = symbols
        self.days = days
        self.failure_rate = failure_rate
        self._rng = random.Random(seed)

    def extract(self) -> list[Record]:
        records: list[Record] = []
        for symbol in self.symbols:
            records.extend(self._fetch_symbol(symbol))
        return records

    @with_retry((TransientAPIError,))
    def _fetch_symbol(self, symbol: str) -> list[Record]:
        if self._rng.random() < self.failure_rate:
            raise TransientAPIError(f"equities API hiccup while fetching {symbol}")

        price = self._rng.uniform(50, 500)
        records = []
        now = datetime.now(timezone.utc)
        for i in range(self.days):
            change_pct = self._rng.uniform(-0.03, 0.03)
            price *= 1 + change_pct
            # Randomly drop a data point to simulate real-world gaps
            # (holidays, missing vendor data).
            if self._rng.random() < 0.03:
                continue
            records.append(
                Record(
                    symbol=symbol,
                    timestamp=(now - timedelta(days=self.days - i)).date().isoformat(),
                    price=round(price, 2),
                    volume=round(self._rng.uniform(1e5, 5e6)),
                    asset_class="equity",
                    source="EquityExtractor(synthetic)",
                )
            )
        return records
