"""Tests for the ETL framework: each stage in isolation, plus swapping stages."""

from __future__ import annotations

import os
import sqlite3
import tempfile

from .core import Pipeline, Record
from .extract import CryptoExtractor, EquityExtractor
from .load import CSVLoader, SQLiteLoader
from .transform import AddMovingAverage, AddReturns, ClipOutliers, DropDuplicates, DropInvalidPrices


def test_equity_extractor_produces_records():
    records = EquityExtractor(symbols=["AAPL"], days=10, failure_rate=0.0, seed=1).extract()
    assert records
    assert all(r.asset_class == "equity" for r in records)
    assert all(r.price > 0 for r in records)


def test_crypto_extractor_produces_records():
    records = CryptoExtractor(symbols=["BTC"], hours=10, failure_rate=0.0, seed=1).extract()
    assert records
    assert all(r.asset_class == "crypto" for r in records)


def test_drop_invalid_prices():
    records = [
        Record(symbol="X", timestamp="1", price=10.0),
        Record(symbol="X", timestamp="2", price=-5.0),
        Record(symbol="X", timestamp="3", price=0.0),
    ]
    cleaned = DropInvalidPrices().transform(records)
    assert len(cleaned) == 1
    assert cleaned[0].timestamp == "1"


def test_drop_duplicates_keeps_first():
    records = [
        Record(symbol="X", timestamp="1", price=10.0),
        Record(symbol="X", timestamp="1", price=99.0),
    ]
    deduped = DropDuplicates().transform(records)
    assert len(deduped) == 1
    assert deduped[0].price == 10.0


def test_clip_outliers():
    records = [Record(symbol="X", timestamp=str(i), price=100.0) for i in range(10)]
    records.append(Record(symbol="X", timestamp="99", price=1_000_000.0))
    clipped = ClipOutliers(n_std=2.0).transform(records)
    assert clipped[-1].price < 1_000_000.0


def test_add_returns_and_moving_average():
    records = [
        Record(symbol="X", timestamp="1", price=100.0),
        Record(symbol="X", timestamp="2", price=110.0),
    ]
    records = AddReturns().transform(records)
    records = AddMovingAverage(window=2).transform(records)
    assert records[0].extra["return_pct"] is None
    assert records[1].extra["return_pct"] == 10.0
    assert records[1].extra["ma_2"] == 105.0


def test_csv_loader_writes_file():
    records = [Record(symbol="X", timestamp="1", price=10.0, asset_class="equity")]
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "out.csv")
        CSVLoader(path).load(records)
        assert os.path.exists(path)
        with open(path) as f:
            content = f.read()
        assert "X" in content and "10.0" in content


def test_sqlite_loader_writes_and_is_idempotent():
    records = [Record(symbol="X", timestamp="1", price=10.0, asset_class="crypto")]
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "out.db")
        loader = SQLiteLoader(db_path, table="prices")
        loader.load(records)
        loader.load(records)  # re-run should not duplicate rows

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
        conn.close()
        assert count == 1


def test_pipeline_is_composable_with_swapped_stages():
    """Same Pipeline shape, different extractor/loader -> proves modularity."""
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = os.path.join(tmp, "equities.csv")
        db_path = os.path.join(tmp, "crypto.db")

        equity_pipeline = Pipeline(
            extractor=EquityExtractor(symbols=["AAPL"], days=5, failure_rate=0.0, seed=1),
            transformers=[DropInvalidPrices(), AddReturns()],
            loader=CSVLoader(csv_path),
        )
        crypto_pipeline = Pipeline(
            extractor=CryptoExtractor(symbols=["BTC"], hours=5, failure_rate=0.0, seed=1),
            transformers=[DropInvalidPrices(), AddReturns()],
            loader=SQLiteLoader(db_path),
        )

        equity_records = equity_pipeline.run()
        crypto_records = crypto_pipeline.run()

        assert os.path.exists(csv_path)
        assert os.path.exists(db_path)
        assert all(r.asset_class == "equity" for r in equity_records)
        assert all(r.asset_class == "crypto" for r in crypto_records)
