"""Cleaning transformers: fix or drop bad records before analysis."""

from __future__ import annotations

from ..core import Record, Transformer


class DropInvalidPrices(Transformer):
    """Drops records with a non-positive or missing price."""

    def transform(self, records: list[Record]) -> list[Record]:
        return [r for r in records if r.price is not None and r.price > 0]


class DropDuplicates(Transformer):
    """Drops records that repeat the same (symbol, timestamp) pair, keeping the first."""

    def transform(self, records: list[Record]) -> list[Record]:
        seen: set[tuple[str, str]] = set()
        deduped = []
        for r in records:
            key = (r.symbol, r.timestamp)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(r)
        return deduped


class ClipOutliers(Transformer):
    """Clips per-symbol prices to within `n_std` standard deviations of the mean.

    Guards downstream analysis against bad ticks (e.g. a fat-fingered
    price spike) without dropping the whole record.
    """

    def __init__(self, n_std: float = 4.0):
        self.n_std = n_std

    def transform(self, records: list[Record]) -> list[Record]:
        by_symbol: dict[str, list[Record]] = {}
        for r in records:
            by_symbol.setdefault(r.symbol, []).append(r)

        for symbol_records in by_symbol.values():
            prices = [r.price for r in symbol_records]
            n = len(prices)
            if n < 2:
                continue
            mean = sum(prices) / n
            variance = sum((p - mean) ** 2 for p in prices) / n
            std = variance**0.5
            if std == 0:
                continue
            lo, hi = mean - self.n_std * std, mean + self.n_std * std
            for r in symbol_records:
                if r.price < lo:
                    r.price = round(lo, 6)
                elif r.price > hi:
                    r.price = round(hi, 6)

        return records
