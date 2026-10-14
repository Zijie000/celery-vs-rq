"""Date-tagged, never-overwrite versioning for daily CSV reports.

Layout on disk (the filenames are the only source of truth, no manifest):

    <root>/<report>/<report>_<YYYY-MM-DD>_v<NNN>.csv

`NNN` is a per-report counter that only ever grows, so every save creates a
brand-new file and a version number is never reused (even after cleanup).
Rollback is non-destructive: it copies an old version forward as a new,
latest version, so history is preserved and the rollback itself is undoable.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True, order=True)
class ReportVersion:
    version: int
    report_date: date
    path: Path


@dataclass(frozen=True)
class RetentionPolicy:
    """A version is kept if it is among the newest `keep_last` OR is at most
    `max_age_days` old (by its date tag). The latest version is always kept."""

    keep_last: int = 7
    max_age_days: int = 30

    def __post_init__(self):
        if self.keep_last < 1:
            raise ValueError("keep_last must be >= 1")
        if self.max_age_days < 0:
            raise ValueError("max_age_days must be >= 0")


class ReportVersionStore:
    def __init__(self, root: str | os.PathLike, retention: RetentionPolicy | None = None):
        """`retention=None` disables automatic cleanup after save/rollback;
        `cleanup()` can still be called explicitly with a policy."""
        self.root = Path(root)
        self.retention = retention

    # ---- writing -------------------------------------------------------

    def save(
        self,
        report: str,
        content: str | bytes,
        report_date: date | None = None,
        skip_unchanged: bool = False,
    ) -> ReportVersion:
        """Store `content` as a new version. Existing files are never touched.

        With `skip_unchanged=True`, identical content to the latest version
        returns that version instead of creating a duplicate.
        """
        data = content.encode("utf-8") if isinstance(content, str) else content
        report_dir = self._report_dir(report)

        if skip_unchanged:
            latest = self.latest(report)
            if latest is not None and latest.path.read_bytes() == data:
                logger.info("%s: content unchanged, keeping v%03d", report, latest.version)
                return latest

        report_dir.mkdir(parents=True, exist_ok=True)
        # Write to a temp file in the same directory, then hard-link it into
        # place: link() fails if the target exists (no overwrite, even under
        # concurrent writers) and readers never see a half-written report.
        fd, tmp = tempfile.mkstemp(dir=report_dir, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            day = report_date or date.today()
            while True:
                version = self._next_version(report)
                target = report_dir / self._filename(report, day, version)
                try:
                    os.link(tmp, target)
                    break
                except FileExistsError:
                    continue  # lost a race for this number; take the next
        finally:
            os.unlink(tmp)

        result = ReportVersion(version, day, target)
        logger.info("%s: saved v%03d (%s)", report, version, day)
        self._auto_cleanup(report)
        return result

    def save_file(self, report: str, path: str | os.PathLike, **kwargs) -> ReportVersion:
        """Store an existing CSV file (e.g. a freshly generated report) as a new version."""
        return self.save(report, Path(path).read_bytes(), **kwargs)

    def rollback(self, report: str, version: int) -> ReportVersion:
        """Make `version` the latest again by copying it forward as a new version.

        Nothing is deleted or modified. The copy is tagged with today's date.
        """
        source = self.get(report, version)
        result = self.save(report, source.path.read_bytes())
        logger.info("%s: rolled back to v%03d as new v%03d", report, version, result.version)
        return result

    # ---- reading -------------------------------------------------------

    def list_versions(self, report: str) -> list[ReportVersion]:
        """All stored versions, oldest first."""
        report_dir = self._report_dir(report)
        if not report_dir.is_dir():
            return []
        pattern = re.compile(
            rf"^{re.escape(report)}_(?P<date>{_DATE_RE.pattern})_v(?P<ver>\d+)\.csv$"
        )
        versions = []
        for entry in report_dir.iterdir():
            m = pattern.match(entry.name)
            if not m:
                continue
            try:
                day = date.fromisoformat(m["date"])
            except ValueError:
                continue
            versions.append(ReportVersion(int(m["ver"]), day, entry))
        return sorted(versions)

    def latest(self, report: str) -> ReportVersion | None:
        versions = self.list_versions(report)
        return versions[-1] if versions else None

    def get(self, report: str, version: int) -> ReportVersion:
        for v in self.list_versions(report):
            if v.version == version:
                return v
        raise KeyError(f"{report}: version {version} not found")

    # ---- cleanup -------------------------------------------------------

    def cleanup(
        self,
        report: str,
        policy: RetentionPolicy | None = None,
        today: date | None = None,
        dry_run: bool = False,
    ) -> list[ReportVersion]:
        """Delete versions outside the retention policy; returns the ones removed
        (or that would be removed, with `dry_run=True`)."""
        policy = policy or self.retention
        if policy is None:
            raise ValueError("no retention policy given and none configured on the store")
        today = today or date.today()
        cutoff = today - timedelta(days=policy.max_age_days)

        versions = self.list_versions(report)
        newest = {v.version for v in versions[-policy.keep_last:]}
        doomed = [v for v in versions if v.version not in newest and v.report_date < cutoff]

        if not dry_run:
            for v in doomed:
                v.path.unlink(missing_ok=True)
                logger.info("%s: removed old v%03d (%s)", report, v.version, v.report_date)
        return doomed

    # ---- internals -----------------------------------------------------

    def _auto_cleanup(self, report: str) -> None:
        if self.retention is not None:
            self.cleanup(report)

    def _report_dir(self, report: str) -> Path:
        if not _NAME_RE.match(report):
            raise ValueError(f"invalid report name {report!r}: use letters, digits, '_' or '-'")
        return self.root / report

    @staticmethod
    def _filename(report: str, day: date, version: int) -> str:
        return f"{report}_{day.isoformat()}_v{version:03d}.csv"

    def _next_version(self, report: str) -> int:
        latest = self.latest(report)
        return latest.version + 1 if latest else 1
