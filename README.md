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
