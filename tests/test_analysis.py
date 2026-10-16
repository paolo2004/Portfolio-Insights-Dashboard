"""Tests for the display formatting and price metrics in ``utils.analysis``."""

import math

import pandas as pd
import pytest
from conftest import StreamlitStop
from utils.analysis import (
    asset_class_from_info,
    calculate_price_metrics,
    format_date_value,
    format_large_number,
    format_number,
    format_percentage,
    format_price,
    get_asset_type,
    get_available_assets,
    get_display_name,
)


class TestFormatNumber:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (1234.5, "1,234.50"),
            (0, "0.00"),
            (-42.5, "-42.50"),
            (1_000_000, "1,000,000.00"),
            ("12", "12.00"),
        ],
    )
    def test_formats_with_thousands_separator(self, value, expected):
        assert format_number(value) == expected

    def test_rounds_half_to_even(self):
        # Python's format() rounds ties to the nearest even digit, so a value
        # ending in exactly 5 does not always round away from zero.
        assert format_number(2.125) == "2.12"
        assert format_number(2.135) == "2.13"

    def test_honours_decimals_argument(self):
        assert format_number(1234.5678, 3) == "1,234.568"
        assert format_number(1234.5678, 0) == "1,235"

    @pytest.mark.parametrize("value", [None, float("nan"), pd.NA, "not a number"])
    def test_unusable_values_become_not_available(self, value):
        assert format_number(value) == "N/A"


class TestFormatLargeNumber:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (2.5e12, "2.50 T"),
            (1e12, "1.00 T"),
            (1.5e9, "1.50 B"),
            (1e9, "1.00 B"),
            (3.2e6, "3.20 M"),
            (1e6, "1.00 M"),
            (999_999, "999,999"),
            (0, "0"),
        ],
    )
    def test_scales_to_the_largest_fitting_unit(self, value, expected):
        assert format_large_number(value) == expected

    def test_negative_values_are_never_abbreviated(self):
        # The thresholds compare the signed value, so negatives fall through to
        # the plain branch. Acceptable for market caps and volumes, which are
        # never negative, but worth pinning so a change is deliberate.
        assert format_large_number(-5e9) == "-5,000,000,000"

    @pytest.mark.parametrize("value", [None, float("nan"), "abc"])
    def test_unusable_values_become_not_available(self, value):
        assert format_large_number(value) == "N/A"


class TestFormatPercentage:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (0.1234, "12.34%"),
            (-0.5, "-50.00%"),
            (0, "0.00%"),
        ],
    )
    def test_fractions_are_scaled_to_percent(self, value, expected):
        assert format_percentage(value) == expected

    def test_fractions_above_one_are_still_scaled(self):
        # 150% revenue growth arrives as 1.5 and must not read as 1.5%.
        assert format_percentage(1.5) == "150.00%"

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (0.41, "0.41%"),
            (12.34, "12.34%"),
            (-250.0, "-250.00%"),
        ],
    )
    def test_values_already_in_percent_are_not_scaled(self, value, expected):
        assert format_percentage(value, is_decimal=False) == expected

    @pytest.mark.parametrize("value", [None, float("nan"), "abc"])
    def test_unusable_values_become_not_available(self, value):
        assert format_percentage(value) == "N/A"


class TestFormatPrice:
    @pytest.mark.parametrize(
        ("currency", "expected"),
        [
            ("USD", "$12.30"),
            ("EUR", "€12.30"),
            ("GBP", "£12.30"),
            ("CHF", "CHF 12.30"),
        ],
    )
    def test_known_currencies_use_their_symbol(self, currency, expected):
        assert format_price(12.3, currency) == expected

    def test_unknown_currency_falls_back_to_its_code(self):
        assert format_price(12.3, "SEK") == "SEK 12.30"

    def test_missing_price_has_no_currency_prefix(self):
        assert format_price(None, "USD") == "N/A"


class TestFormatDateValue:
    def test_converts_unix_seconds_to_iso_date(self):
        assert format_date_value(1_700_000_000) == "2023-11-14"

    @pytest.mark.parametrize("value", [None, 0, ""])
    def test_falsy_timestamps_become_not_available(self, value):
        # Note that epoch 0 is indistinguishable from "missing" here.
        assert format_date_value(value) == "N/A"

    @pytest.mark.parametrize("value", ["abc", object()])
    def test_unparseable_timestamps_become_not_available(self, value):
        assert format_date_value(value) == "N/A"


class TestGetDisplayName:
    def test_crypto_uses_the_name_field(self):
        info = {"name": "Bitcoin", "longName": "Bitcoin USD"}
        assert get_display_name(info, "CRYPTO") == "Bitcoin"

    def test_other_assets_use_the_long_name_field(self):
        info = {"name": "Apple", "longName": "Apple Inc."}
        assert get_display_name(info, "STOCK") == "Apple Inc."

    def test_missing_field_returns_none(self):
        assert get_display_name({}, "STOCK") is None

    def test_missing_field_uses_the_fallback(self):
        assert get_display_name({}, "STOCK", "Apple") == "Apple"
        assert get_display_name({"name": None}, "CRYPTO", "Bitcoin") == "Bitcoin"


class TestAssetClassFromInfo:
    @pytest.mark.parametrize(
        ("quote_type", "expected"),
        [("CRYPTOCURRENCY", "CRYPTO"), ("ETF", "FUND"), ("EQUITY", "STOCK"), (None, "STOCK")],
    )
    def test_maps_the_yahoo_quote_type(self, quote_type, expected):
        assert asset_class_from_info({"quoteType": quote_type}) == expected


class TestGetAssetType:
    @pytest.mark.parametrize(
        ("ticker", "asset_class"),
        [
            ("BTC-USD", "STOCK"),
            ("AAPL", "CRYPTO"),
            ("ETH-USD", "CRYPTO"),
        ],
    )
    def test_crypto_is_detected_by_class_or_suffix(self, ticker, asset_class):
        assert get_asset_type(ticker, asset_class) == "Crypto"

    def test_everything_else_is_a_stock(self):
        assert get_asset_type("AAPL", "STOCK") == "Stock"


def price_history(closes, volumes=None):
    """Build a minimal Yahoo Finance style history frame."""
    frame = pd.DataFrame(
        {
            "Date": pd.date_range("2024-01-01", periods=len(closes), freq="D"),
            "Close": closes,
        }
    )
    if volumes is not None:
        frame["Volume"] = volumes
    return frame


class TestCalculatePriceMetrics:
    def test_derives_price_change_from_the_last_two_closes(self):
        history = price_history([100.0, 110.0], volumes=[5, 7])
        metrics = calculate_price_metrics(history, price_history([90.0, 120.0]), {})

        assert metrics["latest_price"] == 110.0
        assert metrics["price_change"] == pytest.approx(10.0)
        assert metrics["price_change_percent"] == pytest.approx(10.0)
        assert metrics["volume"] == 7

    def test_52_week_range_comes_from_the_one_year_history(self):
        history = price_history([100.0, 110.0])
        one_year = price_history([80.0, 150.0, 95.0])
        metrics = calculate_price_metrics(history, one_year, {})

        assert metrics["high_52_week"] == 150.0
        assert metrics["low_52_week"] == 80.0

    def test_52_week_range_falls_back_to_the_selected_period(self):
        history = price_history([100.0, 110.0])
        metrics = calculate_price_metrics(history, pd.DataFrame(), {})

        assert metrics["high_52_week"] == 110.0
        assert metrics["low_52_week"] == 100.0

    def test_a_single_close_reports_no_change(self):
        metrics = calculate_price_metrics(price_history([100.0]), pd.DataFrame(), {})

        assert metrics["latest_price"] == 100.0
        assert metrics["price_change"] == 0.0
        assert metrics["price_change_percent"] == 0.0

    def test_empty_history_falls_back_to_the_info_price(self):
        metrics = calculate_price_metrics(pd.DataFrame(), pd.DataFrame(), {"currentPrice": 42.0})

        assert metrics["latest_price"] == 42.0
        assert metrics["high_52_week"] is None
        assert metrics["low_52_week"] is None
        assert metrics["volume"] is None

    def test_regular_market_price_is_used_when_current_price_is_missing(self):
        metrics = calculate_price_metrics(
            pd.DataFrame(), pd.DataFrame(), {"regularMarketPrice": 7.5}
        )

        assert metrics["latest_price"] == 7.5

    def test_nan_closes_are_ignored(self):
        history = price_history([100.0, 110.0, float("nan")])
        metrics = calculate_price_metrics(history, pd.DataFrame(), {})

        assert metrics["latest_price"] == 110.0
        assert metrics["price_change"] == pytest.approx(10.0)

    def test_zero_previous_close_does_not_divide_by_zero(self):
        history = price_history([0.0, 110.0])
        metrics = calculate_price_metrics(history, pd.DataFrame(), {})

        assert metrics["price_change_percent"] == 0

    def test_no_price_anywhere_leaves_the_metrics_empty(self):
        metrics = calculate_price_metrics(pd.DataFrame(), pd.DataFrame(), {})

        assert metrics["latest_price"] is None
        assert metrics["price_change"] is None
        assert metrics["price_change_percent"] is None


class TestGetAvailableAssets:
    def test_returns_unique_named_assets_sorted_by_name(self):
        portfolio = pd.DataFrame(
            {
                "name": ["Zeta", "Alpha", "Alpha"],
                "symbol": ["S3", "S1", "S1"],
                "ticker": ["ZZZ", "AAA", "AAA"],
                "asset_class": ["STOCK", "STOCK", "STOCK"],
            }
        )
        assets = get_available_assets(portfolio)

        assert assets["name"].tolist() == ["Alpha", "Zeta"]

    def test_rows_without_a_ticker_are_dropped(self):
        portfolio = pd.DataFrame(
            {
                "name": ["Alpha", "Beta"],
                "symbol": ["S1", "S2"],
                "ticker": ["AAA", None],
                "asset_class": ["STOCK", "STOCK"],
            }
        )
        assets = get_available_assets(portfolio)

        assert assets["name"].tolist() == ["Alpha"]

    def test_stops_when_no_asset_has_a_ticker(self):
        portfolio = pd.DataFrame(
            {
                "name": ["Alpha"],
                "symbol": ["S1"],
                "ticker": [None],
                "asset_class": ["STOCK"],
            }
        )
        with pytest.raises(StreamlitStop):
            get_available_assets(portfolio)


def test_format_number_and_price_agree_on_missing_values():
    """The price formatter must not print a lone currency symbol."""
    assert math.isnan(float("nan"))
    assert format_price(float("nan"), "EUR") == "N/A"
