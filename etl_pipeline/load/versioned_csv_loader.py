"""CSV loader that stores each run as a new date-tagged version."""

from __future__ import annotations

import os
import tempfile

from report_versioning import ReportVersionStore

from ..core import Loader, Record
from .csv_loader import CSVLoader


class VersionedCSVLoader(Loader):
    """Renders records with `CSVLoader`, then saves them as a new version in a
    `ReportVersionStore` instead of overwriting a fixed path."""

    def __init__(self, store: ReportVersionStore, report: str, skip_unchanged: bool = False):
        self.store = store
        self.report = report
        self.skip_unchanged = skip_unchanged

    def load(self, records: list[Record]) -> None:
        fd, tmp = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        try:
            CSVLoader(tmp).load(records)
            self.store.save_file(self.report, tmp, skip_unchanged=self.skip_unchanged)
        finally:
            os.unlink(tmp)
