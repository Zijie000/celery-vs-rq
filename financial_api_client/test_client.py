"""Tests for FinancialAPIClient's retry behavior, using mocks to simulate
a flaky API deterministically instead of relying on randomness.
"""

from unittest.mock import MagicMock

import pytest

from client import FinancialAPIClient, QuoteFetchError
from flaky_api import RateLimitError, ServiceUnavailableError, TimeoutError


def make_client(mock_api, max_attempts=5):
    return FinancialAPIClient(mock_api, max_attempts=max_attempts, initial_wait=0.001, max_wait=0.01)


def test_succeeds_on_first_try():
    mock_api = MagicMock()
    mock_api.get_quote.return_value = {"symbol": "AAPL", "price": 123.45, "currency": "USD"}

    client = make_client(mock_api)
    result = client.get_quote("AAPL")

    assert result["price"] == 123.45
    assert mock_api.get_quote.call_count == 1


def test_retries_then_succeeds():
    mock_api = MagicMock()
    mock_api.get_quote.side_effect = [
        RateLimitError("429"),
        ServiceUnavailableError("503"),
        {"symbol": "MSFT", "price": 300.0, "currency": "USD"},
    ]

    client = make_client(mock_api)
    result = client.get_quote("MSFT")

    assert result["price"] == 300.0
    assert mock_api.get_quote.call_count == 3


def test_exhausts_retries_and_raises_quote_fetch_error():
    mock_api = MagicMock()
    mock_api.get_quote.side_effect = TimeoutError("timed out")

    client = make_client(mock_api, max_attempts=3)

    with pytest.raises(QuoteFetchError):
        client.get_quote("TSLA")

    assert mock_api.get_quote.call_count == 3


def test_non_transient_error_is_not_retried():
    mock_api = MagicMock()
    mock_api.get_quote.side_effect = ValueError("bad symbol")

    client = make_client(mock_api)

    with pytest.raises(ValueError):
        client.get_quote("???")

    assert mock_api.get_quote.call_count == 1


def test_logs_retry_warnings_and_final_error(caplog):
    mock_api = MagicMock()
    mock_api.get_quote.side_effect = RateLimitError("429")

    client = make_client(mock_api, max_attempts=2)

    with caplog.at_level("WARNING", logger="financial_api_client"):
        with pytest.raises(QuoteFetchError):
            client.get_quote("NFLX")

    messages = [record.message for record in caplog.records]
    assert any("Retrying" in m for m in messages)
    assert any("Giving up fetching quote for NFLX" in m for m in messages)
