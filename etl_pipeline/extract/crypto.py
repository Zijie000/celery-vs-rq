"""Crypto price extractor.

Stands in for a real crypto market-data API (e.g. Coinbase, Binance,
CoinGecko). Crypto trades continuously (no market holidays/weekends) and
is far more volatile than equities — the synthetic generator reflects
both differences so the demo shows genuinely distinct asset-class
behavior, not just a relabeled copy of the equities extractor.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from ..core import Extractor, Record
from .base import with_retry


class TransientAPIError(Exception):
    """Simulated transient failure (rate limit / timeout / 5xx)."""


class CryptoExtractor(Extractor):
    """Fetches a synthetic hourly price series for crypto symbols."""

    def __init__(
        self,
        symbols: list[str],
        hours: int = 48,
        failure_rate: float = 0.15,
        seed: int | None = None,
    ):
        self.symbols = symbols
        self.hours = hours
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
            raise TransientAPIError(f"crypto API hiccup while fetching {symbol}")

        price = self._rng.uniform(0.5, 60000)
        records = []
        now = datetime.now(timezone.utc)
        for i in range(self.hours):
            change_pct = self._rng.uniform(-0.08, 0.08)  # crypto: higher volatility
            price *= 1 + change_pct
            if self._rng.random() < 0.02:
                continue
            records.append(
                Record(
                    symbol=symbol,
                    timestamp=(now - timedelta(hours=self.hours - i)).isoformat(),
                    price=round(price, 6),
                    volume=round(self._rng.uniform(10, 1e4), 4),
                    asset_class="crypto",
                    source="CryptoExtractor(synthetic)",
                )
            )
        return records
