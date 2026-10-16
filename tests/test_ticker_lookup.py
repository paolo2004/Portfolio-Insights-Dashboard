"""Tests for the ISIN → Yahoo Finance ticker resolution in ``utils.ticker_lookup``.

Every outbound call (OpenFIGI and Yahoo Finance) is mocked, so the suite runs
offline and never depends on live market data.
"""

import pandas as pd
import pytest
import requests
from utils import ticker_lookup
from utils.ticker_lookup import (
    _format_yahoo_symbol,
    _validate_yahoo_ticker,
    get_crypto_ticker,
    get_ticker_from_isin,
)


class FakeResponse:
    """Minimal stand-in for a ``requests`` response."""

    def __init__(self, payload, error=None):
        self._payload = payload
        self._error = error

    def raise_for_status(self):
        if self._error is not None:
            raise self._error

    def json(self):
        return self._payload


def figi_payload(*candidates):
    """Build an OpenFIGI response body from (ticker, exchCode) pairs."""
    return [{"data": [{"ticker": t, "exchCode": e} for t, e in candidates]}]


@pytest.fixture
def openfigi(monkeypatch):
    """Capture OpenFIGI requests and return a configurable response."""
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "timeout": timeout})
        response = fake_post.response
        if isinstance(response, Exception):
            raise response
        return response

    fake_post.calls = calls
    fake_post.response = FakeResponse(figi_payload())
    monkeypatch.setattr(ticker_lookup.requests, "post", fake_post)
    return fake_post


class TestFormatYahooSymbol:
    @pytest.mark.parametrize(
        ("ticker", "exch_code", "expected"),
        [
            ("SAP", "XET", "SAP.DE"),
            ("SAP", "DE", "SAP.DE"),
            ("AIR", "FP", "AIR.PA"),
            ("VALE", "BR", "VALE.SA"),
            ("600519", "CG", "600519.SS"),
            ("SHOP", "CN", "SHOP.TO"),
            ("SAP", "GY", "SAP.DE"),
        ],
    )
    def test_maps_exchange_codes_to_yahoo_suffixes(self, ticker, exch_code, expected):
        assert _format_yahoo_symbol(ticker, exch_code) == expected

    def test_us_listings_carry_no_suffix(self):
        assert _format_yahoo_symbol("aapl", "US") == "AAPL"

    def test_unmapped_exchange_falls_back_to_the_bare_ticker(self):
        assert _format_yahoo_symbol("AAPL", "ZZZ") == "AAPL"

    def test_normalises_case_and_whitespace(self):
        assert _format_yahoo_symbol("  sap  ", "  xet  ") == "SAP.DE"

    @pytest.mark.parametrize("ticker", [None, "", "   "])
    def test_missing_ticker_returns_none(self, ticker):
        assert _format_yahoo_symbol(ticker, "US") is None

    def test_missing_exchange_code_returns_the_bare_ticker(self):
        assert _format_yahoo_symbol("AAPL", None) == "AAPL"


class TestGetCryptoTicker:
    def test_appends_the_usd_pair_suffix(self):
        assert get_crypto_ticker({"asset_class": "CRYPTO", "symbol": "btc"}) == "BTC-USD"

    def test_works_on_a_dataframe_row(self):
        row = pd.Series({"asset_class": "crypto", "symbol": "ETH"})
        assert get_crypto_ticker(row) == "ETH-USD"

    def test_non_crypto_rows_are_skipped(self):
        assert get_crypto_ticker({"asset_class": "STOCK", "symbol": "AAPL"}) is None

    def test_rows_without_a_symbol_are_skipped(self):
        assert get_crypto_ticker({"asset_class": "CRYPTO", "symbol": ""}) is None
        assert get_crypto_ticker({"asset_class": "CRYPTO"}) is None


class TestValidateYahooTicker:
    def _patch_history(self, monkeypatch, history):
        class FakeTicker:
            def __init__(self, symbol):
                self.symbol = symbol

            def history(self, **kwargs):
                if isinstance(history, Exception):
                    raise history
                return history

        monkeypatch.setattr(ticker_lookup.yf, "Ticker", FakeTicker)

    def test_a_symbol_with_price_history_is_valid(self, monkeypatch):
        self._patch_history(monkeypatch, pd.DataFrame({"Close": [1.0]}))

        assert _validate_yahoo_ticker("AAPL") is True

    def test_a_symbol_without_price_history_is_invalid(self, monkeypatch):
        self._patch_history(monkeypatch, pd.DataFrame())

        assert _validate_yahoo_ticker("NOPE") is False

    def test_a_failing_lookup_is_invalid(self, monkeypatch):
        self._patch_history(monkeypatch, RuntimeError("network down"))

        assert _validate_yahoo_ticker("AAPL") is False

    @pytest.mark.parametrize("symbol", [None, ""])
    def test_missing_symbol_is_invalid_without_a_lookup(self, symbol, monkeypatch):
        def fail(*args, **kwargs):
            raise AssertionError("should not reach the network")

        monkeypatch.setattr(ticker_lookup.yf, "Ticker", fail)

        assert _validate_yahoo_ticker(symbol) is False


class TestGetTickerFromIsin:
    @pytest.mark.parametrize("isin", [None, "", "   "])
    def test_missing_isin_skips_the_request(self, isin, openfigi):
        assert get_ticker_from_isin(isin) is None
        assert openfigi.calls == []

    def test_returns_the_first_candidate_that_yahoo_finance_knows(self, openfigi, monkeypatch):
        openfigi.response = FakeResponse(figi_payload(("SAP", "XET")))
        monkeypatch.setattr(
            ticker_lookup, "_validate_yahoo_ticker", lambda symbol: symbol == "SAP.DE"
        )

        assert get_ticker_from_isin("DE0007164600") == "SAP.DE"

    def test_skips_candidates_yahoo_finance_does_not_know(self, openfigi, monkeypatch):
        openfigi.response = FakeResponse(figi_payload(("BOGUS", "XET"), ("SAP", "DE")))
        monkeypatch.setattr(
            ticker_lookup, "_validate_yahoo_ticker", lambda symbol: symbol == "SAP.DE"
        )

        assert get_ticker_from_isin("DE0007164600") == "SAP.DE"

    def test_never_falls_back_to_the_unsuffixed_ticker(self, openfigi, monkeypatch):
        # A bare "SAP" could be a different listing or company than the ISIN names.
        openfigi.response = FakeResponse(figi_payload(("SAP", "XET")))
        monkeypatch.setattr(ticker_lookup, "_validate_yahoo_ticker", lambda symbol: symbol == "SAP")

        assert get_ticker_from_isin("DE0007164600") is None

    def test_unmapped_exchanges_are_skipped(self, openfigi, monkeypatch):
        openfigi.response = FakeResponse(figi_payload(("SAP", "ZZ"), ("SAP", "GY")))
        tried = []

        def validate(symbol):
            tried.append(symbol)
            return True

        monkeypatch.setattr(ticker_lookup, "_validate_yahoo_ticker", validate)

        assert get_ticker_from_isin("DE0007164600") == "SAP.DE"
        assert tried == ["SAP.DE"]

    def test_returns_none_when_no_candidate_is_valid(self, openfigi, monkeypatch):
        openfigi.response = FakeResponse(figi_payload(("SAP", "XET")))
        monkeypatch.setattr(ticker_lookup, "_validate_yahoo_ticker", lambda symbol: False)

        assert get_ticker_from_isin("DE0007164600") is None

    def test_candidates_without_an_exchange_code_are_ignored(self, openfigi, monkeypatch):
        openfigi.response = FakeResponse([{"data": [{"ticker": "SAP"}]}])
        monkeypatch.setattr(ticker_lookup, "_validate_yahoo_ticker", lambda symbol: True)

        assert get_ticker_from_isin("DE0007164600") is None

    def test_sends_the_isin_uppercased_with_a_timeout(self, openfigi, monkeypatch):
        openfigi.response = FakeResponse(figi_payload(("SAP", "XET")))
        monkeypatch.setattr(ticker_lookup, "_validate_yahoo_ticker", lambda symbol: True)

        get_ticker_from_isin(" de0007164600 ")

        assert openfigi.calls[0]["json"] == [{"idType": "ID_ISIN", "idValue": "DE0007164600"}]
        assert openfigi.calls[0]["timeout"] == 15

    @pytest.mark.parametrize(
        "payload",
        [[], {}, [{"data": []}], [{}]],
    )
    def test_unusable_payloads_return_none(self, payload, openfigi, monkeypatch):
        openfigi.response = FakeResponse(payload)
        monkeypatch.setattr(ticker_lookup, "_validate_yahoo_ticker", lambda symbol: True)

        assert get_ticker_from_isin("DE0007164600") is None

    def test_a_network_failure_returns_none(self, openfigi):
        openfigi.response = requests.exceptions.ConnectionError("no route to host")

        assert get_ticker_from_isin("DE0007164600") is None

    def test_an_http_error_returns_none(self, openfigi):
        openfigi.response = FakeResponse(
            None, error=requests.exceptions.HTTPError("429 Too Many Requests")
        )

        assert get_ticker_from_isin("DE0007164600") is None

    def test_failures_are_not_cached(self, openfigi, monkeypatch):
        monkeypatch.setattr(ticker_lookup, "_validate_yahoo_ticker", lambda symbol: True)
        openfigi.response = requests.exceptions.ConnectionError("no route to host")
        assert get_ticker_from_isin("DE0007164600") is None

        openfigi.response = FakeResponse(figi_payload(("SAP", "XET")))
        assert get_ticker_from_isin("DE0007164600") == "SAP.DE"

    def test_repeated_lookups_are_cached(self, openfigi, monkeypatch):
        openfigi.response = FakeResponse(figi_payload(("SAP", "XET")))
        monkeypatch.setattr(ticker_lookup, "_validate_yahoo_ticker", lambda symbol: True)

        get_ticker_from_isin("DE0007164600")
        get_ticker_from_isin("DE0007164600")

        assert len(openfigi.calls) == 1
