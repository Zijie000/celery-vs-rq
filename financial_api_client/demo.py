"""Demo: fetch quotes for a batch of symbols from the flaky API.

Run with: python3 demo.py
"""

import logging

from client import FinancialAPIClient, QuoteFetchError
from flaky_api import FlakyFinancialAPI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

SYMBOLS = ["AAPL", "MSFT", "GOOG", "AMZN", "TSLA"]


def main():
    api = FlakyFinancialAPI(failure_rate=0.6, latency=0.05, seed=42)
    client = FinancialAPIClient(api, max_attempts=5)

    for symbol in SYMBOLS:
        try:
            quote = client.get_quote(symbol)
            print(f"{symbol}: ${quote['price']}")
        except QuoteFetchError as exc:
            print(f"{symbol}: FAILED — {exc}")


if __name__ == "__main__":
    main()
