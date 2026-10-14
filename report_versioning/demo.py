"""Demo: a week of daily report runs, a bad day, rollback, and cleanup.

Run: python3 -m report_versioning.demo
"""

from __future__ import annotations

import logging
import tempfile
from datetime import date, timedelta

from .store import ReportVersionStore, RetentionPolicy

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def show(store: ReportVersionStore, report: str, title: str) -> None:
    print(f"\n{title}")
    for v in store.list_versions(report):
        print(f"  v{v.version:03d}  {v.report_date}  {v.path.name}")


def main():
    with tempfile.TemporaryDirectory() as root:
        store = ReportVersionStore(root)  # cleanup is explicit below so we can show it
        today = date.today()

        # 10 daily runs of a metrics report; today's export is corrupted.
        for i in range(10):
            day = today - timedelta(days=9 - i)
            body = "metric,value\nsharpe,NaN\n" if i == 9 else f"metric,value\nsharpe,{1.0 + i / 10:.2f}\n"
            store.save("daily_metrics", body, report_date=day)
        show(store, "daily_metrics", "After 10 daily runs:")

        print("\nLatest:", store.latest("daily_metrics").path.name)
        bad = store.latest("daily_metrics")
        print("Rolling back to v009 (last good report before the bad export)...")
        restored = store.rollback("daily_metrics", 9)
        print(f"New latest: v{restored.version:03d} (copy of v009); v{bad.version:03d} is still on disk")
        show(store, "daily_metrics", "After rollback:")

        policy = RetentionPolicy(keep_last=4, max_age_days=5)
        would_remove = store.cleanup("daily_metrics", policy, dry_run=True)
        print(f"\nDry run, policy {policy}: would remove {[v.version for v in would_remove]}")
        store.cleanup("daily_metrics", policy)
        show(store, "daily_metrics", "After cleanup:")


if __name__ == "__main__":
    main()
