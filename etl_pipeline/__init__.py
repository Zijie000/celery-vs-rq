"""A modular ETL framework for financial time series data.

Three independently replaceable stages — Extractor, Transformer, Loader —
wired together by Pipeline. See `demo.py` for usage.
"""

from .core import Extractor, Loader, Pipeline, Record, Transformer

__all__ = ["Extractor", "Loader", "Pipeline", "Record", "Transformer"]
