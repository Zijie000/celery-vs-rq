"""Tests for the report versioning store."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from etl_pipeline.core import Record
from etl_pipeline.load.versioned_csv_loader import VersionedCSVLoader

from .store import ReportVersionStore, RetentionPolicy

DAY = date(2026, 10, 14)


def test_save_tags_by_date_and_never_overwrites(tmp_path):
    store = ReportVersionStore(tmp_path)
    v1 = store.save("metrics", "a\n1\n", report_date=DAY)
    v2 = store.save("metrics", "a\n2\n", report_date=DAY)  # same day, same report

    assert v1.path.name == "metrics_2026-10-14_v001.csv"
    assert v2.path.name == "metrics_2026-10-14_v002.csv"
    assert v1.path.read_text() == "a\n1\n"
    assert v2.path.read_text() == "a\n2\n"


def test_no_temp_files_left_behind(tmp_path):
    store = ReportVersionStore(tmp_path)
    store.save("metrics", "x", report_date=DAY)
    assert [p.name for p in (tmp_path / "metrics").iterdir()] == ["metrics_2026-10-14_v001.csv"]


def test_skip_unchanged(tmp_path):
    store = ReportVersionStore(tmp_path)
    v1 = store.save("metrics", "same", report_date=DAY)
    again = store.save("metrics", "same", report_date=DAY, skip_unchanged=True)
    changed = store.save("metrics", "different", report_date=DAY, skip_unchanged=True)

    assert again == v1
    assert changed.version == 2
    assert len(store.list_versions("metrics")) == 2


def test_reports_are_isolated(tmp_path):
    store = ReportVersionStore(tmp_path)
    store.save("equities", "e", report_date=DAY)
    store.save("crypto", "c", report_date=DAY)
    assert [v.version for v in store.list_versions("equities")] == [1]
    assert [v.version for v in store.list_versions("crypto")] == [1]


def test_invalid_report_name_rejected(tmp_path):
    store = ReportVersionStore(tmp_path)
    for bad in ["../evil", "a/b", "", ".hidden"]:
        with pytest.raises(ValueError):
            store.save(bad, "x")


def test_rollback_copies_forward_without_deleting_history(tmp_path):
    store = ReportVersionStore(tmp_path)
    store.save("metrics", "good", report_date=DAY - timedelta(days=2))
    store.save("metrics", "bad", report_date=DAY - timedelta(days=1))

    restored = store.rollback("metrics", 1)

    assert restored.version == 3
    assert store.latest("metrics") == restored
    assert restored.path.read_text() == "good"
    assert [v.path.read_text() for v in store.list_versions("metrics")] == ["good", "bad", "good"]


def test_rollback_unknown_version(tmp_path):
    store = ReportVersionStore(tmp_path)
    store.save("metrics", "x", report_date=DAY)
    with pytest.raises(KeyError):
        store.rollback("metrics", 99)


def _seed_daily(store, n, end=DAY):
    for i in range(n):
        store.save("metrics", f"day{i}", report_date=end - timedelta(days=n - 1 - i))


def test_cleanup_removes_only_versions_that_are_both_old_and_beyond_keep_last(tmp_path):
    store = ReportVersionStore(tmp_path)
    _seed_daily(store, 10)  # v1 (oldest, 9 days ago) .. v10 (today)

    removed = store.cleanup("metrics", RetentionPolicy(keep_last=3, max_age_days=5), today=DAY)

    # cutoff = 5 days ago: v1..v4 are older than that; v8..v10 are within keep_last
    assert [v.version for v in removed] == [1, 2, 3, 4]
    assert [v.version for v in store.list_versions("metrics")] == [5, 6, 7, 8, 9, 10]


def test_cleanup_keeps_old_versions_within_keep_last(tmp_path):
    store = ReportVersionStore(tmp_path)
    _seed_daily(store, 3)
    removed = store.cleanup("metrics", RetentionPolicy(keep_last=5, max_age_days=0), today=DAY + timedelta(days=100))
    assert removed == []


def test_cleanup_always_keeps_latest(tmp_path):
    store = ReportVersionStore(tmp_path)
    _seed_daily(store, 3)
    store.cleanup("metrics", RetentionPolicy(keep_last=1, max_age_days=0), today=DAY + timedelta(days=100))
    assert [v.version for v in store.list_versions("metrics")] == [3]


def test_cleanup_dry_run_deletes_nothing(tmp_path):
    store = ReportVersionStore(tmp_path)
    _seed_daily(store, 10)
    doomed = store.cleanup("metrics", RetentionPolicy(keep_last=1, max_age_days=0), today=DAY, dry_run=True)
    assert len(doomed) == 9
    assert len(store.list_versions("metrics")) == 10


def test_auto_cleanup_runs_after_save(tmp_path):
    store = ReportVersionStore(tmp_path, retention=RetentionPolicy(keep_last=2, max_age_days=0))
    for i in range(4):
        store.save("metrics", f"d{i}", report_date=DAY - timedelta(days=10 - i))
    assert [v.version for v in store.list_versions("metrics")] == [3, 4]


def test_version_numbers_not_reused_after_cleanup(tmp_path):
    store = ReportVersionStore(tmp_path, retention=RetentionPolicy(keep_last=1, max_age_days=0))
    store.save("metrics", "a", report_date=DAY - timedelta(days=5))
    store.save("metrics", "b", report_date=DAY - timedelta(days=4))  # v1 cleaned
    v3 = store.save("metrics", "c", report_date=DAY - timedelta(days=3))
    assert v3.version == 3


def test_rolled_back_copy_survives_auto_cleanup(tmp_path):
    store = ReportVersionStore(tmp_path)
    store.save("metrics", "good", report_date=DAY - timedelta(days=60))
    store.save("metrics", "bad", report_date=DAY - timedelta(days=59))
    store.retention = RetentionPolicy(keep_last=1, max_age_days=30)

    restored = store.rollback("metrics", 1)

    assert [v.version for v in store.list_versions("metrics")] == [restored.version]
    assert restored.path.read_text() == "good"


def test_cleanup_requires_a_policy(tmp_path):
    with pytest.raises(ValueError):
        ReportVersionStore(tmp_path).cleanup("metrics")


def test_versioned_csv_loader_creates_new_version_each_run(tmp_path):
    store = ReportVersionStore(tmp_path)
    loader = VersionedCSVLoader(store, "equities")
    loader.load([Record(symbol="AAPL", timestamp="1", price=10.0)])
    loader.load([Record(symbol="AAPL", timestamp="1", price=11.0)])

    versions = store.list_versions("equities")
    assert len(versions) == 2
    assert "10.0" in versions[0].path.read_text()
    assert "11.0" in versions[1].path.read_text()
