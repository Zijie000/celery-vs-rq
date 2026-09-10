"""Feature transformers: derive analysis-ready fields, sorted per symbol."""

from __future__ import annotations

from ..core import Record, Transformer


def _sorted_by_symbol(records: list[Record]) -> dict[str, list[Record]]:
    by_symbol: dict[str, list[Record]] = {}
    for r in records:
        by_symbol.setdefault(r.symbol, []).append(r)
    for symbol_records in by_symbol.values():
        symbol_records.sort(key=lambda r: r.timestamp)
    return by_symbol


class AddReturns(Transformer):
    """Adds `extra["return_pct"]`: percent change from the prior observation."""

    def transform(self, records: list[Record]) -> list[Record]:
        for symbol_records in _sorted_by_symbol(records).values():
            prev_price = None
            for r in symbol_records:
                if prev_price is not None and prev_price != 0:
                    r.extra["return_pct"] = round((r.price - prev_price) / prev_price * 100, 4)
                else:
                    r.extra["return_pct"] = None
                prev_price = r.price
        return records


class AddMovingAverage(Transformer):
    """Adds `extra["ma_<window>"]`: trailing simple moving average of price."""

    def __init__(self, window: int = 5):
        self.window = window

    def transform(self, records: list[Record]) -> list[Record]:
        key = f"ma_{self.window}"
        for symbol_records in _sorted_by_symbol(records).values():
            prices: list[float] = []
            for r in symbol_records:
                prices.append(r.price)
                window_slice = prices[-self.window :]
                r.extra[key] = round(sum(window_slice) / len(window_slice), 6)
        return records
