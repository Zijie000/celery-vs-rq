"""Benchmark SQLite vs DuckDB on ~5 years of daily OHLCV data.

Measures setup cost, ingest, ad-hoc query latency, pandas integration and
disk usage, then writes results.json and comparison.png next to this file.

Run: python3 -m db_benchmark.benchmark [--symbols 500] [--repeats 5]
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import logging
import os
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

OUT_DIR = Path(__file__).parent
ENGINES = ["SQLite", "DuckDB", "DuckDB (1 thread)"]
TRADING_DAYS = 252 * 5

# SQL is identical across engines except where date handling differs. SQLite
# stores dates as ISO text, DuckDB as DATE.
QUERIES: dict[str, dict[str, str]] = {
    "Symbol lookup\n(1 symbol, 1 yr)": {
        "sqlite": "SELECT * FROM prices WHERE symbol = 'SYM0042' AND date >= '2024-01-01' AND date < '2025-01-01'",
        "duckdb": "SELECT * FROM prices WHERE symbol = 'SYM0042' AND date >= DATE '2024-01-01' AND date < DATE '2025-01-01'",
    },
    "Per-symbol stats\n(GROUP BY symbol)": {
        "sqlite": "SELECT symbol, AVG(close), MIN(low), MAX(high), SUM(volume) FROM prices GROUP BY symbol",
        "duckdb": "SELECT symbol, AVG(close), MIN(low), MAX(high), SUM(volume) FROM prices GROUP BY symbol",
    },
    "Monthly avg close\n(GROUP BY symbol, month)": {
        "sqlite": "SELECT symbol, substr(date, 1, 7) AS m, AVG(close) FROM prices GROUP BY symbol, m",
        "duckdb": "SELECT symbol, date_trunc('month', date) AS m, AVG(close) FROM prices GROUP BY symbol, m",
    },
    "20-day moving average\n(window function)": {
        "sqlite": """SELECT AVG(ma) FROM (SELECT AVG(close) OVER (
                       PARTITION BY symbol ORDER BY date ROWS 19 PRECEDING) AS ma FROM prices)""",
        "duckdb": """SELECT AVG(ma) FROM (SELECT AVG(close) OVER (
                       PARTITION BY symbol ORDER BY date ROWS 19 PRECEDING) AS ma FROM prices)""",
    },
    "Top 10 daily moves\n(LAG + sort)": {
        "sqlite": """SELECT symbol, date, ret FROM (
                       SELECT symbol, date, close / LAG(close) OVER (PARTITION BY symbol ORDER BY date) - 1 AS ret
                       FROM prices) WHERE ret IS NOT NULL ORDER BY ABS(ret) DESC LIMIT 10""",
        "duckdb": """SELECT symbol, date, ret FROM (
                       SELECT symbol, date, close / LAG(close) OVER (PARTITION BY symbol ORDER BY date) - 1 AS ret
                       FROM prices) WHERE ret IS NOT NULL ORDER BY ABS(ret) DESC LIMIT 10""",
    },
    "Top-5 volume per day\n(ROW_NUMBER per date)": {
        "sqlite": """SELECT AVG(volume) FROM (SELECT volume, ROW_NUMBER() OVER (
                       PARTITION BY date ORDER BY volume DESC) AS rn FROM prices) WHERE rn <= 5""",
        "duckdb": """SELECT AVG(volume) FROM (SELECT volume, ROW_NUMBER() OVER (
                       PARTITION BY date ORDER BY volume DESC) AS rn FROM prices) WHERE rn <= 5""",
    },
}


def generate_prices(n_symbols: int, seed: int = 42) -> pd.DataFrame:
    """Synthetic daily OHLCV: a geometric random walk per symbol, ending 2025-12-31."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end="2025-12-31", periods=TRADING_DAYS)
    n = len(dates)

    start = rng.uniform(10, 400, size=(n_symbols, 1))
    daily = rng.normal(0.0003, 0.018, size=(n_symbols, n))
    close = start * np.exp(np.cumsum(daily, axis=1))
    open_ = close * np.exp(rng.normal(0, 0.004, size=(n_symbols, n)))
    spread = np.abs(rng.normal(0, 0.008, size=(n_symbols, n)))
    high = np.maximum(open_, close) * (1 + spread)
    low = np.minimum(open_, close) * (1 - spread)
    volume = rng.lognormal(mean=13, sigma=0.6, size=(n_symbols, n)).astype(np.int64)

    return pd.DataFrame(
        {
            "symbol": np.repeat([f"SYM{i:04d}" for i in range(n_symbols)], n),
            "date": np.tile(dates, n_symbols),
            "open": open_.ravel().round(4),
            "high": high.ravel().round(4),
            "low": low.ravel().round(4),
            "close": close.ravel().round(4),
            "volume": volume.ravel(),
        }
    )


def timed(fn, repeats: int) -> float:
    """Median wall-clock seconds over `repeats` runs, after one warm-up run."""
    fn()
    runs = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        runs.append(time.perf_counter() - t0)
    return statistics.median(runs)


def setup_costs() -> dict:
    """Install footprint and cold import time (fresh interpreter, best of 3)."""

    def import_ms(module: str) -> float:
        runs = []
        for _ in range(3):
            t0 = time.perf_counter()
            subprocess.run([sys.executable, "-c", f"import {module}"], check=True)
            runs.append(time.perf_counter() - t0)
        return min(runs) * 1000

    dist = importlib.metadata.distribution("duckdb")
    install_mb = sum(f.locate().stat().st_size for f in dist.files if f.locate().exists()) / 1e6
    return {
        "SQLite": {"import_ms": import_ms("sqlite3"), "install_mb": 0.0, "pip_install": False},
        "DuckDB": {"import_ms": import_ms("duckdb"), "install_mb": install_mb, "pip_install": True},
    }


def build_sqlite(path: str, df: pd.DataFrame) -> float:
    rows = df.assign(date=df["date"].dt.strftime("%Y-%m-%d"))
    t0 = time.perf_counter()
    con = sqlite3.connect(path)
    con.execute(
        """CREATE TABLE prices (symbol TEXT, date TEXT, open REAL, high REAL, low REAL,
           close REAL, volume INTEGER, PRIMARY KEY (symbol, date)) WITHOUT ROWID"""
    )
    con.executemany("INSERT INTO prices VALUES (?,?,?,?,?,?,?)", rows.itertuples(index=False, name=None))
    con.commit()
    con.close()
    return time.perf_counter() - t0


def build_duckdb(path: str, df: pd.DataFrame) -> float:
    t0 = time.perf_counter()
    con = duckdb.connect(path)
    con.execute(
        """CREATE TABLE prices (symbol VARCHAR, date DATE, open DOUBLE, high DOUBLE, low DOUBLE,
           close DOUBLE, volume BIGINT)"""
    )
    con.execute("INSERT INTO prices SELECT * FROM df")  # reads the DataFrame in place
    con.execute("CHECKPOINT")
    con.close()
    return time.perf_counter() - t0


def run_benchmark(n_symbols: int, repeats: int) -> dict:
    df = generate_prices(n_symbols)
    logger.info("Generated %d rows (%d symbols x %d days)", len(df), n_symbols, TRADING_DAYS)

    with tempfile.TemporaryDirectory() as tmp:
        sqlite_path, duck_path, csv_path = (os.path.join(tmp, n) for n in ("p.sqlite", "p.duckdb", "p.csv"))
        df.to_csv(csv_path, index=False)

        results: dict = {
            "rows": len(df),
            "symbols": n_symbols,
            "repeats": repeats,
            "versions": {"sqlite": sqlite3.sqlite_version, "duckdb": duckdb.__version__, "pandas": pd.__version__},
            "cpu_count": os.cpu_count(),
            "setup": setup_costs(),
        }

        ingest = {"SQLite": build_sqlite(sqlite_path, df), "DuckDB": build_duckdb(duck_path, df)}
        ingest["DuckDB (1 thread)"] = ingest["DuckDB"]  # same load; thread cap only affects queries
        results["ingest_s"] = ingest
        results["disk_mb"] = {
            "CSV (reference)": os.path.getsize(csv_path) / 1e6,
            "SQLite": os.path.getsize(sqlite_path) / 1e6,
            "DuckDB": os.path.getsize(duck_path) / 1e6,
        }
        logger.info("Ingest: %s | Disk MB: %s", ingest, results["disk_mb"])

        sq = sqlite3.connect(sqlite_path)
        d_all = duckdb.connect(duck_path, read_only=True)
        d_one = duckdb.connect(duck_path, read_only=True)
        d_one.execute("SET threads = 1")
        runners = {
            "SQLite": lambda q: sq.execute(q["sqlite"]).fetchall(),
            "DuckDB": lambda q: d_all.execute(q["duckdb"]).fetchall(),
            "DuckDB (1 thread)": lambda q: d_one.execute(q["duckdb"]).fetchall(),
        }

        # Both engines must agree before timings mean anything.
        for name, q in QUERIES.items():
            a, b = runners["SQLite"](q), runners["DuckDB"](q)
            assert _same(a, b), f"result mismatch for {name!r}"

        results["queries_s"] = {
            engine: {name: timed(lambda: run(q), repeats) for name, q in QUERIES.items()}
            for engine, run in runners.items()
        }

        d_mem = duckdb.connect()
        d_mem.register("df", df)  # zero-copy view over the DataFrame

        # Python integration: moving rows between the DB and pandas.
        bulk = "date >= '2024-01-01'"  # ~1/5 of the table
        results["pandas_s"] = {
            "SQLite": {
                "Query → DataFrame": timed(
                    lambda: pd.read_sql_query(f"SELECT * FROM prices WHERE {bulk}", sq), repeats
                ),
            },
            "DuckDB": {
                "Query → DataFrame": timed(
                    lambda: d_all.execute(f"SELECT * FROM prices WHERE {bulk}").df(), repeats
                ),
                "SQL on a DataFrame\n(no load step)": timed(
                    lambda: d_mem.execute("SELECT symbol, AVG(close) FROM df GROUP BY symbol").fetchall(), repeats
                ),
            },
        }
        # SQLite has no zero-copy path: the same aggregate means loading first.
        results["pandas_s"]["SQLite"]["SQL on a DataFrame\n(no load step)"] = timed(
            lambda: _sqlite_on_dataframe(df), max(1, repeats // 2)
        )
        sq.close()
        d_all.close()
        d_one.close()
    return results


def _sqlite_on_dataframe(df: pd.DataFrame) -> list:
    con = sqlite3.connect(":memory:")
    df.assign(date=df["date"].dt.strftime("%Y-%m-%d")).to_sql("df", con, index=False)
    try:
        return con.execute("SELECT symbol, AVG(close) FROM df GROUP BY symbol").fetchall()
    finally:
        con.close()


def _same(a: list, b: list) -> bool:
    if len(a) != len(b):
        return False
    key = lambda r: tuple(str(x)[:7] if not isinstance(x, float) else round(x, 6) for x in r)  # noqa: E731
    for ra, rb in zip(sorted(a, key=key), sorted(b, key=key)):
        for x, y in zip(ra, rb):
            if isinstance(x, float) and isinstance(y, (int, float)):
                if abs(x - y) > 1e-6 * max(1.0, abs(x)):
                    return False
            elif not isinstance(x, float) and str(x)[:7] != str(y)[:7]:
                return False
    return True


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", type=int, default=500)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    results = run_benchmark(args.symbols, args.repeats)
    (OUT_DIR / "results.json").write_text(json.dumps(results, indent=2))

    from .chart import render

    render(results, OUT_DIR / "comparison.png")
    print(f"Wrote {OUT_DIR / 'results.json'} and {OUT_DIR / 'comparison.png'}")


if __name__ == "__main__":
    main()
