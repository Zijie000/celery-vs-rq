"""CSV file loader."""

from __future__ import annotations

import csv
import os

from ..core import Loader, Record

BASE_FIELDS = ["symbol", "timestamp", "price", "volume", "asset_class", "source"]


class CSVLoader(Loader):
    """Writes records to a CSV file, one row per record.

    Any keys present in `Record.extra` (e.g. return_pct, ma_5) are
    flattened into their own columns.
    """

    def __init__(self, path: str):
        self.path = path

    def load(self, records: list[Record]) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)

        extra_fields: list[str] = []
        for r in records:
            for key in r.extra:
                if key not in extra_fields:
                    extra_fields.append(key)
        fieldnames = BASE_FIELDS + extra_fields

        with open(self.path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in records:
                row = {
                    "symbol": r.symbol,
                    "timestamp": r.timestamp,
                    "price": r.price,
                    "volume": r.volume,
                    "asset_class": r.asset_class,
                    "source": r.source,
                }
                row.update(r.extra)
                writer.writerow(row)
