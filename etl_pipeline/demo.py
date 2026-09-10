"""Demo: run the same Pipeline shape against two different asset classes.

Equities -> CSV and crypto -> SQLite use different Extractors and
different Loaders, but share the Pipeline orchestrator and several
Transformer stages untouched — proving each stage is swappable
independently of the others.

Run: python3 -m etl_pipeline.demo
"""

from __future__ import annotations

import logging
import sqlite3

from .core import Pipeline
from .extract import CryptoExtractor, EquityExtractor
from .load import CSVLoader, SQLiteLoader
from .transform import AddMovingAverage, AddReturns, ClipOutliers, DropDuplicates, DropInvalidPrices

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def build_equity_pipeline() -> Pipeline:
    return Pipeline(
        name="equities",
        extractor=EquityExtractor(symbols=["AAPL", "MSFT", "GOOG"], days=30, seed=1),
        transformers=[
            DropInvalidPrices(),
            DropDuplicates(),
            ClipOutliers(n_std=4.0),
            AddReturns(),
            AddMovingAverage(window=5),
        ],
        loader=CSVLoader(path="etl_pipeline/output/equities.csv"),
    )


def build_crypto_pipeline() -> Pipeline:
    return Pipeline(
        name="crypto",
        extractor=CryptoExtractor(symbols=["BTC", "ETH"], hours=48, seed=2),
        transformers=[
            DropInvalidPrices(),
            DropDuplicates(),
            ClipOutliers(n_std=4.0),
            AddReturns(),
            AddMovingAverage(window=5),
        ],
        loader=SQLiteLoader(db_path="etl_pipeline/output/market_data.db", table="crypto_prices"),
    )


def main():
    equity_records = build_equity_pipeline().run()
    crypto_records = build_crypto_pipeline().run()

    print(f"\nEquities: {len(equity_records)} records -> etl_pipeline/output/equities.csv")
    if equity_records:
        print("Sample:", equity_records[-1])

    print(f"\nCrypto: {len(crypto_records)} records -> etl_pipeline/output/market_data.db")
    if crypto_records:
        print("Sample:", crypto_records[-1])

    conn = sqlite3.connect("etl_pipeline/output/market_data.db")
    count = conn.execute("SELECT COUNT(*) FROM crypto_prices").fetchone()[0]
    conn.close()
    print(f"\nVerified: {count} rows in crypto_prices table")


if __name__ == "__main__":
    main()
