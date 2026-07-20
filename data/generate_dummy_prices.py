"""
Generate synthetic stock price data shared by both Celery and RQ moving average tasks.
Uses a pure random walk (no real market data) to produce a realistic-looking price series
for workload benchmarking.
"""
import random


def generate_prices(n: int = 5000, start_price: float = 100.0, seed: int = None) -> list[float]:
    """Generate a random-walk price series of n data points."""
    if seed is not None:
        random.seed(seed)
    prices = [start_price]
    for _ in range(n - 1):
        change_pct = random.uniform(-0.02, 0.02)  # ±2% change per step
        new_price = prices[-1] * (1 + change_pct)
        prices.append(round(new_price, 4))
    return prices


if __name__ == "__main__":
    sample = generate_prices(10, seed=42)
    print(sample)
