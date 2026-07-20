"""
Shared financial analysis logic used by both Celery and RQ.
Ensures both queue systems run identical workloads for a fair comparison.
"""
import time


def moving_average(prices: list[float], window: int = 20) -> list[float]:
    """Compute Simple Moving Average (SMA) in pure Python without pandas/numpy,
    to avoid extra dependencies in worker subprocesses and keep CPU usage realistic.
    """
    if window <= 0 or window > len(prices):
        raise ValueError(f"Invalid window size: window={window}, len(prices)={len(prices)}")

    result = []
    running_sum = sum(prices[:window])
    result.append(running_sum / window)

    for i in range(window, len(prices)):
        running_sum += prices[i] - prices[i - window]
        result.append(running_sum / window)

    return result


def run_financial_job(prices: list[float], windows: tuple[int, ...] = (5, 20, 50)) -> dict:
    """Simulate a financial analysis job: compute multiple moving averages (e.g. 5/20/50-day)
    over the same price series and record elapsed time for queue performance comparison.
    """
    start = time.perf_counter()
    result = {}
    for w in windows:
        result[f"ma_{w}"] = moving_average(prices, w)
    elapsed = time.perf_counter() - start

    return {
        "input_size": len(prices),
        "windows": windows,
        "elapsed_seconds": round(elapsed, 6),
        # Return only the last value of each MA to avoid flooding the message queue/logs
        "last_values": {k: round(v[-1], 4) for k, v in result.items()},
    }


def simulate_failure(prices: list[float], fail: bool = True) -> dict:
    """Reliability test task: optionally raises an exception to test retry/failure handling."""
    if fail:
        raise RuntimeError("Simulated task failure for testing Celery/RQ retry and failure handling")
    return run_financial_job(prices)
