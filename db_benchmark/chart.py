"""Render the SQLite vs DuckDB comparison chart from benchmark results."""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

# Validated categorical slots 1-3 (see dataviz palette); color follows the engine.
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e3e2de"
COLORS = {"SQLite": "#2a78d6", "DuckDB": "#eb6834", "DuckDB (1 thread)": "#1baf7a", "CSV (reference)": "#a9a8a2"}


def _fmt_s(seconds: float) -> str:
    ms = seconds * 1000
    if seconds >= 1:
        return f"{seconds:.2f} s"
    return f"{ms:.1f} ms" if ms < 10 else f"{ms:.0f} ms"


def _ms_ticks(ax):
    from matplotlib.ticker import FuncFormatter

    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: _fmt_s(x)))
    ax.xaxis.set_minor_formatter(FuncFormatter(lambda x, _: ""))


def _style(ax, title: str, note: str = ""):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold", color=INK, pad=26 if note else 8)
    if note:
        ax.text(0, 1.015, note, transform=ax.transAxes, fontsize=8.5, color=INK_2, va="bottom")
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9, length=0)


def _bars_h(ax, groups: list[str], series: dict[str, list[float]], fmt, log: bool):
    n = len(series)
    h = 0.78 / n
    for i, (name, values) in enumerate(series.items()):
        ys = [g + (i - (n - 1) / 2) * h for g in range(len(groups))]
        bars = ax.barh(ys, values, height=h - 0.05, color=COLORS[name], edgecolor=SURFACE, linewidth=2, zorder=3)
        for bar, v in zip(bars, values):
            ax.text(v * 1.08 if log else v, bar.get_y() + bar.get_height() / 2, " " + fmt(v),
                    va="center", fontsize=8, color=INK_2)
    ax.set_yticks(range(len(groups)), groups)
    ax.invert_yaxis()
    if log:
        ax.set_xscale("log")
    ax.xaxis.grid(True, color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def _bars_v(ax, labels: list[str], values: list[float], colors: list[str], fmt, log: bool = False):
    bars = ax.bar(labels, values, width=0.55, color=colors, edgecolor=SURFACE, linewidth=2, zorder=3)
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, v * (1.1 if log else 1.0) + (0 if log else max(values) * 0.015),
                fmt(v), ha="center", va="bottom", fontsize=9, color=INK)
    if log:
        ax.set_yscale("log")
    ax.yaxis.grid(True, color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def render(results: dict, out_path: Path) -> None:
    q = results["queries_s"]
    names = list(q["SQLite"])
    speedups = [q["SQLite"][n] / q["DuckDB"][n] for n in names]
    analytical = [s for s in speedups if s >= 1]  # point lookups are the exception, called out separately
    lookup = names[0]
    v = results["versions"]

    fig = plt.figure(figsize=(14, 10.5), facecolor=SURFACE)
    gs = fig.add_gridspec(2, 3, height_ratios=[1.5, 1], hspace=0.55, wspace=0.28,
                          left=0.14, right=0.97, top=0.78, bottom=0.07)

    fig.text(0.03, 0.955, "SQLite vs DuckDB on 5 years of daily OHLCV prices", fontsize=18,
             fontweight="bold", color=INK)
    fig.text(0.03, 0.915,
             f"DuckDB runs analytical queries {min(analytical):.0f}–{max(analytical):.0f}× faster "
             f"(median {statistics.median(analytical):.0f}×) and stores the data in "
             f"{results['disk_mb']['SQLite'] / results['disk_mb']['DuckDB']:.1f}× less space; "
             f"SQLite wins the indexed point lookup ({_fmt_s(q['SQLite'][lookup])} vs {_fmt_s(q['DuckDB'][lookup])}).",
             fontsize=10.5, color=INK_2)
    fig.text(0.03, 0.89,
             f"{results['rows']:,} rows · {results['symbols']} symbols × 1,260 trading days · median of "
             f"{results['repeats']} warm runs · SQLite {v['sqlite']}, DuckDB {v['duckdb']}, "
             f"pandas {v['pandas']} · {results['cpu_count']} CPU cores",
             fontsize=8.5, color=INK_2)

    fig.legend(
        handles=[Patch(color=COLORS[k], label=k) for k in ("SQLite", "DuckDB", "DuckDB (1 thread)")],
        loc="upper left", bbox_to_anchor=(0.03, 0.87), ncol=3, frameon=False, fontsize=10,
        labelcolor=INK_2,
    )

    # A: query latency (all three engines, log scale)
    ax = fig.add_subplot(gs[0, :])
    _bars_h(ax, names, {e: [q[e][n] for n in names] for e in ENGINES_ORDER}, _fmt_s, log=True)
    for i, s in enumerate(speedups):
        ax.text(0.995, i, f"{s:.1f}× faster" if s >= 1 else f"{1 / s:.1f}× slower", transform=ax.get_yaxis_transform(),
                ha="right", va="center", fontsize=10, fontweight="bold", color=INK)
    ax.text(0.995, -0.75, "DuckDB vs SQLite", transform=ax.get_yaxis_transform(), ha="right", va="bottom",
            fontsize=8.5, color=INK_2)
    ax.set_xlim(right=ax.get_xlim()[1] * 6)
    _ms_ticks(ax)
    ax.set_xlabel("Query latency, lower is better (log scale)", fontsize=9, color=INK_2)
    _style(ax, "Ad-hoc query latency")

    # B: ingest
    ax = fig.add_subplot(gs[1, 0])
    ing = results["ingest_s"]
    _bars_v(ax, ["SQLite", "DuckDB"], [ing["SQLite"], ing["DuckDB"]],
            [COLORS["SQLite"], COLORS["DuckDB"]], _fmt_s)
    ax.set_ylabel("seconds", fontsize=9, color=INK_2)
    ax.set_ylim(top=max(ing["SQLite"], ing["DuckDB"]) * 1.15)
    _style(ax, "Load time", "From an in-memory DataFrame\n(SQLite table has a primary key)")

    # C: disk
    ax = fig.add_subplot(gs[1, 1])
    d = results["disk_mb"]
    order = ["CSV (reference)", "SQLite", "DuckDB"]
    _bars_v(ax, order, [d[k] for k in order], [COLORS[k] for k in order], lambda x: f"{x:.0f} MB")
    ax.set_ylabel("MB", fontsize=9, color=INK_2)
    ax.set_ylim(top=max(d.values()) * 1.15)
    _style(ax, "Disk usage", "Database file after load\n+ checkpoint")

    # D: pandas integration
    ax = fig.add_subplot(gs[1, 2])
    p = results["pandas_s"]
    tasks = list(p["DuckDB"])
    x = range(len(tasks))
    w = 0.36
    for i, eng in enumerate(("SQLite", "DuckDB")):
        vals = [p[eng][t] for t in tasks]
        pos = [xi + (i - 0.5) * w for xi in x]
        bars = ax.bar(pos, vals, width=w - 0.04, color=COLORS[eng], edgecolor=SURFACE, linewidth=2, zorder=3)
        for b, val in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, val * 1.1, _fmt_s(val), ha="center", va="bottom",
                    fontsize=8.5, color=INK)
    ax.set_yscale("log")
    ax.set_xticks(list(x), tasks)
    ax.set_ylim(top=ax.get_ylim()[1] * 2)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    _style(ax, "Python / pandas integration", "Log scale. For SQLite, 'no load step'\nmeans copying the DataFrame in first")

    fig.savefig(out_path, dpi=160, facecolor=SURFACE)
    plt.close(fig)


ENGINES_ORDER = ["SQLite", "DuckDB", "DuckDB (1 thread)"]

if __name__ == "__main__":
    src = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "results.json")
    render(json.loads(src.read_text()), src.with_name("comparison.png"))
