# job-queue-comparison

A benchmark comparing Celery and RQ task queues using a synthetic financial analysis workload (moving average calculations).

For the full comparison and conclusions, see [`REPORT.md`](./REPORT.md).

## Project Structure

```
job-queue-comparison/
├── celery_demo/
│   ├── tasks.py       # Celery task definitions
│   ├── worker.py      # Helper script to launch workers
│   └── run_test.py    # Submit tasks and measure timing
├── rq_demo/
│   ├── tasks.py        # RQ task definitions
│   ├── worker.py        # Helper script to launch workers
│   └── run_test.py      # Submit tasks and measure timing
├── data/
│   ├── generate_dummy_prices.py  # Generate synthetic stock price data
│   └── analysis.py               # Shared moving average calculation logic
├── financial_api_client/
│   ├── flaky_api.py    # Simulated flaky financial quotes API
│   ├── client.py        # Client with tenacity-based retry + exponential backoff
│   ├── demo.py           # Runnable demo with logging
│   └── test_client.py    # Mock-based tests of the retry behavior
├── etl_pipeline/
│   ├── core.py            # Record, Extractor/Transformer/Loader interfaces, Pipeline
│   ├── extract/           # EquityExtractor, CryptoExtractor (independently swappable)
│   ├── transform/         # Cleaning (dedupe, outliers) and feature (returns, MA) stages
│   ├── load/               # CSVLoader, SQLiteLoader (independently swappable)
│   ├── demo.py             # Runs equities->CSV and crypto->SQLite pipelines
│   └── test_pipeline.py   # Unit tests per stage + a composed-pipeline test
├── report_versioning/
│   ├── store.py         # ReportVersionStore: save / list / rollback / cleanup
│   ├── demo.py           # Runnable demo: daily runs, bad day, rollback, cleanup
│   └── test_store.py    # Tests for versioning, rollback, and retention
├── requirements.txt
└── REPORT.md            # Full comparison report
```

## Quick Start

### 0. Install dependencies

```bash
# Redis — started via Docker Compose (see docker-compose.yml)
docker compose up -d

pip3 install -r requirements.txt
```

### 1. Test Celery

```bash
cd celery_demo
celery -A tasks worker --loglevel=info --concurrency=4 &
python run_test.py
```

### 2. Test RQ

```bash
cd rq_demo
# Note: --with-scheduler is required; without it, delayed retry tests will time out. See worker.py for details.
rq worker -u redis://localhost:6379/2 --with-scheduler financial_jobs &
python run_test.py
```

Each `run_test.py` runs three test scenarios:
1. Single task: submit → receive result latency
2. Batch of 50 tasks processed concurrently
3. Auto-retry behavior on an intentionally failing task

### 3. Retry mechanism for a flaky financial API

```bash
cd financial_api_client
python3 demo.py          # runs a batch of quote fetches against a simulated flaky API
python3 -m pytest -v     # runs the mock-based retry tests
```

`client.py` wraps calls to a simulated flaky API (`flaky_api.py`) with
[`tenacity`](https://tenacity.readthedocs.io/): retries only on transient
errors (rate limits, 503s, timeouts), exponential backoff with jitter, a
capped attempt count, and logging of each retry attempt and the final
success/failure.

### 4. Modular ETL pipeline framework

```bash
python3 -m etl_pipeline.demo     # runs equities->CSV and crypto->SQLite pipelines
python3 -m pytest etl_pipeline/test_pipeline.py -v
```

`etl_pipeline/` is a small, modular ETL framework for financial time
series data. Each stage is a swappable interface:

- **Extract** (`etl_pipeline/extract/`): `EquityExtractor` and
  `CryptoExtractor` pull synthetic (offline, no API key needed) but
  realistically-shaped price series — retrying transient failures with
  the same `tenacity` backoff policy as `financial_api_client`.
- **Transform** (`etl_pipeline/transform/`): composable cleaning stages
  (`DropInvalidPrices`, `DropDuplicates`, `ClipOutliers`) and feature
  stages (`AddReturns`, `AddMovingAverage`), applied in sequence.
- **Load** (`etl_pipeline/load/`): `CSVLoader` and `SQLiteLoader` persist
  the final records.
- **Pipeline** (`etl_pipeline/core.py`): wires one Extractor, a list of
  Transformers, and one Loader together and runs them in order.

`demo.py` builds two pipelines that share the same `Pipeline` orchestrator
and several transform stages, but use different extractors and loaders —
equities go to a CSV file, crypto goes to a SQLite table — demonstrating
that any stage can be replaced without touching the others.

### 5. File versioning for daily reports

```bash
python3 -m report_versioning.demo
python3 -m pytest report_versioning -v
```

`report_versioning/` stores each generated CSV as a new file,
`<root>/<report>/<report>_<YYYY-MM-DD>_v<NNN>.csv`, and never overwrites:
files are written to a temp file and hard-linked into place, so an existing
version can't be clobbered and readers never see a partial report. `NNN` is
a per-report counter that is never reused.

```python
store = ReportVersionStore("reports", retention=RetentionPolicy(keep_last=7, max_age_days=30))
store.save("daily_metrics", csv_text)         # -> new version, auto-cleans afterwards
store.list_versions("daily_metrics")
store.rollback("daily_metrics", 9)            # copies v009 forward as the new latest
store.cleanup("daily_metrics", dry_run=True)  # preview what would be deleted
```

- **Rollback** is non-destructive: it copies the old version forward as a
  new latest version, so the bad version stays on disk and the rollback can
  itself be rolled back.
- **Cleanup** deletes a version only if it is outside the newest `keep_last`
  *and* older than `max_age_days` (by its date tag, not mtime). The latest
  version is always kept. It runs automatically after save/rollback when a
  retention policy is configured.
- `etl_pipeline.load.VersionedCSVLoader` plugs the store into an ETL
  `Pipeline` in place of `CSVLoader`.
