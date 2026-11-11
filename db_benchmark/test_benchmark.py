"""Tests for the SQLite vs DuckDB benchmark (tiny dataset, correctness only)."""

from __future__ import annotations

from .benchmark import QUERIES, generate_prices, run_benchmark
from .chart import render


def test_generate_prices_is_valid_ohlcv_and_deterministic():
    df = generate_prices(3)
    assert len(df) == 3 * 1260
    assert df.duplicated(["symbol", "date"]).sum() == 0
    assert (df["high"] >= df[["open", "close"]].max(axis=1)).all()
    assert (df["low"] <= df[["open", "close"]].min(axis=1)).all()
    assert (df["volume"] > 0).all()
    assert df.equals(generate_prices(3))


def test_engines_agree_and_results_are_complete(tmp_path):
    # run_benchmark asserts SQLite and DuckDB return the same rows for every query
    results = run_benchmark(n_symbols=3, repeats=1)
    for engine in ("SQLite", "DuckDB", "DuckDB (1 thread)"):
        assert set(results["queries_s"][engine]) == set(QUERIES)
    assert results["disk_mb"]["DuckDB"] > 0 and results["disk_mb"]["SQLite"] > 0

    render(results, tmp_path / "chart.png")
    assert (tmp_path / "chart.png").stat().st_size > 10_000
