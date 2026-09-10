"""Core types and interfaces shared by every ETL stage.

The framework has three replaceable stage kinds — Extractor, Transformer,
Loader — plus a Pipeline that wires one of each together. Any class that
implements the right interface can be swapped in without touching the
other stages, so a new data source, cleaning rule, or storage backend is
a new small class, not a change to existing code.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger("etl_pipeline")


@dataclass
class Record:
    """One time-series observation, normalized across asset classes."""

    symbol: str
    timestamp: str
    price: float
    volume: float | None = None
    asset_class: str = "unknown"
    source: str = "unknown"
    extra: dict = field(default_factory=dict)


class Extractor(ABC):
    """Pulls raw records for one or more symbols from a data source."""

    @abstractmethod
    def extract(self) -> list[Record]:
        ...


class Transformer(ABC):
    """Applies one cleaning/transformation step to a list of records."""

    @abstractmethod
    def transform(self, records: list[Record]) -> list[Record]:
        ...


class Loader(ABC):
    """Persists the final records somewhere."""

    @abstractmethod
    def load(self, records: list[Record]) -> None:
        ...


class Pipeline:
    """Orchestrates extract -> transform(s) -> load.

    Each stage is injected, so any stage can be replaced independently
    (e.g. swap CryptoExtractor for EquityExtractor, or CSVLoader for
    SQLiteLoader) without changing the Pipeline or the other stages.
    """

    def __init__(
        self,
        extractor: Extractor,
        transformers: list[Transformer],
        loader: Loader,
        name: str = "pipeline",
    ):
        self.extractor = extractor
        self.transformers = transformers
        self.loader = loader
        self.name = name

    def run(self) -> list[Record]:
        logger.info("[%s] extracting from %s", self.name, type(self.extractor).__name__)
        records = self.extractor.extract()
        logger.info("[%s] extracted %d records", self.name, len(records))

        for stage in self.transformers:
            before = len(records)
            records = stage.transform(records)
            logger.info(
                "[%s] transform %s: %d -> %d records",
                self.name,
                type(stage).__name__,
                before,
                len(records),
            )

        logger.info("[%s] loading %d records via %s", self.name, len(records), type(self.loader).__name__)
        self.loader.load(records)
        logger.info("[%s] done", self.name)
        return records
