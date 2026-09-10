"""SQLite database loader."""

from __future__ import annotations

import json
import os
import sqlite3

from ..core import Loader, Record


class SQLiteLoader(Loader):
    """Writes records into a SQLite table, replacing any prior rows for the
    same (symbol, timestamp) pair so re-running the pipeline is idempotent.
    """

    def __init__(self, db_path: str, table: str = "prices"):
        self.db_path = db_path
        self.table = table

    def load(self, records: list[Record]) -> None:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table} (
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    price REAL NOT NULL,
                    volume REAL,
                    asset_class TEXT,
                    source TEXT,
                    extra TEXT,
                    PRIMARY KEY (symbol, timestamp)
                )
                """
            )
            conn.executemany(
                f"""
                INSERT OR REPLACE INTO {self.table}
                    (symbol, timestamp, price, volume, asset_class, source, extra)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        r.symbol,
                        r.timestamp,
                        r.price,
                        r.volume,
                        r.asset_class,
                        r.source,
                        json.dumps(r.extra),
                    )
                    for r in records
                ],
            )
            conn.commit()
        finally:
            conn.close()
