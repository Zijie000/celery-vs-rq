# Python Task Queue Benchmark: Celery vs. RQ

**Test environment**: Local Redis 7.0 (broker + result backend), Python 3.12
**Workload**: Synthetic financial analysis — computing 5/20/50-day moving averages over randomly generated price series
**Code structure**: See `celery_demo/`, `rq_demo/`, and `data/` (both sides share the same computation logic for a fair comparison)

---

## 1. Setup Complexity

| | Celery | RQ |
|---|---|---|
| Dependencies | `celery` + 9 indirect deps (billiard, kombu, click family, vine, tzlocal, etc.) | `rq` + 3 deps (click, croniter, redis) |
| Task definition | Requires a `Celery()` app instance and `@app.task` decorator; tasks need a `name`, serialization config, etc. | Plain Python functions — no decorator, no app object required |
| Task file size (this demo) | `tasks.py` — 44 lines | `tasks.py` — 16 lines |
| Starting a worker | `celery -A tasks worker --loglevel=info --concurrency=4` (multiple subprocesses within one process) | `rq worker -u redis://... financial_jobs` (single-process, single-threaded; concurrency requires multiple processes) |
| **Gotchas** | None — retry works out of the box | **Real gotcha found in testing**: when using `Retry(interval=[...])` for delayed retries, `--with-scheduler` is required when launching the worker (or run a separate `rq scheduler` process). Without it, failed tasks get stuck in the "scheduled" registry and are never re-queued, causing the caller to time out. This is not prominently documented and was discovered through hands-on testing. |

**Verdict**: RQ's core API is simpler and more beginner-friendly ("a function is a task"). However, advanced features like delayed retries require non-obvious extra configuration. Celery has a steeper initial learning curve (app object, decorators, serialization config), but features like retry and task orchestration are built-in and require no extra processes.

---

## 2. Performance

Two benchmark runs were conducted; results were stable. Representative figures:

| Scenario | Celery | RQ |
|---|---|---|
| Single task (5000 price points, 3 MAs): submit → result wall time | 0.115s – 0.182s | **0.065s** (faster) |
| Single task internal compute time | ~0.0026s | ~0.002s (nearly identical — same logic) |
| Batch of 50 tasks, concurrent (4 workers): total wall time | **1.02s** (avg 0.020s/task) | 1.36s – 1.45s (avg 0.027–0.029s/task) |

**Analysis**:
- **Single-task latency**: RQ is faster. Celery's message protocol (JSON + kombu envelope) and richer task metadata add overhead per submission.
- **Batch throughput**: Celery wins slightly. The key difference is the worker model — Celery uses `prefork`, spawning multiple subprocesses within one worker process; RQ is single-process single-threaded by default, requiring multiple separate worker processes for concurrency (4 were used here). Celery's scheduling across those subprocesses is more mature.

**Summary**: RQ wins on low-latency single tasks; Celery wins slightly on high-concurrency batch throughput — though the gap at this workload scale is modest (single-digit to ~30%).

---

## 3. Reliability

Both support task retry on failure and both worked correctly in testing:

| | Celery | RQ |
|---|---|---|
| Retry configuration | Decorator params: `autoretry_for=(RuntimeError,)`, `retry_backoff=1`, `max_retries=3` | Call-site param: `Retry(max=3, interval=[1,2,4])` |
| Extra process needed for retry | No — handled by the worker | **Yes** — delayed retries require `--with-scheduler` |
| Test result | Correctly entered `FAILURE` state after 3 retries; `.get()` raised the original exception | Correctly entered `FAILED` state after 3 retries (requires scheduler) |
| Result persistence | Result backend (Redis db1 in this test); results are queryable | Redis-native result storage; retained for 500s by default (configurable via `result_ttl`) |
| Worker crash handling | `visibility_timeout` mechanism prevents task loss at the broker level | `job_timeout` + heartbeat detects dead workers; stale jobs can be re-queued |

**Verdict**: Both are production-ready for retry scenarios. Celery's retry is more self-contained (handled within the worker, no extra process needed); RQ's delayed retry requires remembering the `--with-scheduler` flag, which is an easy pitfall to miss.

---

## 4. Suitability for Distributed Workloads

| | Celery | RQ |
|---|---|---|
| Broker support | Redis, RabbitMQ, Amazon SQS, and more | Redis only |
| Task orchestration | Rich: `chain` (sequential), `group` (parallel), `chord` (parallel + aggregate), scheduled tasks (`celery beat`) | Basic: supports `depends_on` for task dependencies, but lacks Celery's complex workflow primitives |
| Multi-machine deployment | Mature — workers can be distributed across any number of machines sharing a broker; rich monitoring ecosystem (Flower) | Supported — workers connect to the same Redis; simpler monitoring ecosystem (`rq-dashboard`) |
| Scalability ceiling | Better suited for large-scale, complex distributed task topologies (e.g. multi-stage financial data pipelines) | Better suited for small-to-medium scale, simpler queue-and-execute patterns |

**Verdict**: For scenarios involving **complex task orchestration** (e.g. "fetch from multiple sources in parallel → aggregate → compute metrics → generate report"), Celery's `chain`/`chord` primitives are a significant advantage. For simple **"enqueue → run → collect result"** patterns, RQ is sufficient and lighter weight.

---

## 5. Overall Recommendation

- **Favor RQ** when: the team is small, tasks are simple (e.g. single-step calculations like moving averages), quick onboarding is a priority, and minimal configuration overhead is desired.
- **Favor Celery** when: tasks have complex dependencies or multi-stage orchestration needs (e.g. multi-factor analysis pipelines), scheduled/recurring tasks are needed (e.g. nightly batch runs after market close), there is a possibility of switching to RabbitMQ/SQS later, or mature visual monitoring (Flower) is required.

Given a quantitative/financial analysis context, if the workload will eventually involve chained or branching pipelines ("multi-factor computation → portfolio optimization → risk validation"), **Celery's orchestration primitives will pay off long-term**. If the current need is simply to offload isolated compute tasks asynchronously, **RQ is faster to set up and cheaper to maintain**.

---

## Appendix: Reproducing the Benchmark

```bash
# 1. Start Redis
redis-server --daemonize yes

# 2. Celery test
cd celery_demo
celery -A tasks worker --loglevel=info --concurrency=4 &
python run_test.py

# 3. RQ test (--with-scheduler is required — see worker.py for details)
cd ../rq_demo
rq worker -u redis://localhost:6379/2 --with-scheduler financial_jobs &
python run_test.py
```
