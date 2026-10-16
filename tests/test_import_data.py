"""Tests for file import, validation and the data-loaded guard."""

import io
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st
from conftest import FakeUpload, StreamlitStop
from utils import import_data
from utils.import_data import check_if_data_loaded, load_data, validate_data

CSV_HEADER = (
    "date,type,name,symbol,asset_class,shares,amount,fee,tax,currency,"
    "counterparty_iban,payment_reference\n"
)
CSV_ROW = "2024-01-05,BUY,Apple,US0378331005,STOCK,10,-1000,-1,0,EUR,DE12345,order 1\n"


def csv_upload(text, name="export.csv"):
    return FakeUpload(text.encode("ISO-8859-1"), name)


def excel_upload(frame, name="export.xlsx"):
    buffer = io.BytesIO()
    frame.to_excel(buffer, index=False)
    buffer.seek(0)
    return FakeUpload(buffer.getvalue(), name)


@pytest.fixture
def no_isin_lookup(monkeypatch):
    """Replace the OpenFIGI lookup with a deterministic offline stub."""
    calls = []

    def fake_lookup(isin):
        calls.append(isin)
        return f"TICK:{isin}"

    monkeypatch.setattr(import_data, "get_ticker_from_isin", fake_lookup)
    return calls


def test_project_structure_exists():
    assert Path("app").is_dir()
    assert Path("app/utils/import_data.py").is_file()
    assert Path("app/utils/analysis.py").is_file()
    assert Path("app/main.py").is_file()


class TestLoadDataParsing:
    def test_reads_a_comma_separated_csv(self, no_isin_lookup):
        frame = load_data(csv_upload(CSV_HEADER + CSV_ROW))

        assert len(frame) == 1
        assert frame.loc[0, "name"] == "Apple"
        assert frame.loc[0, "amount"] == -1000

    def test_detects_a_semicolon_separated_csv(self, no_isin_lookup):
        text = (CSV_HEADER + CSV_ROW).replace(",", ";")
        frame = load_data(csv_upload(text))

        assert len(frame) == 1
        assert frame.loc[0, "amount"] == -1000

    def test_reads_a_txt_export(self, no_isin_lookup):
        frame = load_data(csv_upload(CSV_HEADER + CSV_ROW, name="export.txt"))

        assert len(frame) == 1

    def test_reads_an_excel_export(self, no_isin_lookup):
        source = pd.read_csv(io.StringIO(CSV_HEADER + CSV_ROW))
        frame = load_data(excel_upload(source))

        assert len(frame) == 1
        assert frame.loc[0, "name"] == "Apple"

    def test_uppercase_extensions_are_accepted(self, no_isin_lookup):
        frame = load_data(csv_upload(CSV_HEADER + CSV_ROW, name="EXPORT.CSV"))

        assert len(frame) == 1

    @pytest.mark.parametrize("name", ["export.pdf", "export.json", "export"])
    def test_unsupported_file_types_are_rejected(self, name):
        with pytest.raises(ValueError, match="Unsupported file type"):
            load_data(csv_upload(CSV_HEADER + CSV_ROW, name=name))


class TestLoadDataNormalisation:
    def test_dates_become_datetimes(self, no_isin_lookup):
        frame = load_data(csv_upload(CSV_HEADER + CSV_ROW))

        assert pd.api.types.is_datetime64_any_dtype(frame["date"])

    def test_a_month_column_is_derived_from_the_date(self, no_isin_lookup):
        frame = load_data(csv_upload(CSV_HEADER + CSV_ROW))

        assert frame.loc[0, "month"] == "2024-01"

    def test_an_existing_month_column_is_kept(self, no_isin_lookup):
        text = CSV_HEADER.rstrip("\n") + ",month\n" + CSV_ROW.rstrip("\n") + ",custom\n"
        frame = load_data(csv_upload(text))

        assert frame.loc[0, "month"] == "custom"

    def test_unparseable_dates_become_missing_rather_than_raising(self, no_isin_lookup):
        row = CSV_ROW.replace("2024-01-05", "not a date")
        frame = load_data(csv_upload(CSV_HEADER + row))

        assert pd.isna(frame.loc[0, "date"])

    def test_numeric_columns_are_coerced_and_blanks_become_zero(self, no_isin_lookup):
        row = CSV_ROW.replace(",-1,0,EUR", ",,n/a,EUR")
        frame = load_data(csv_upload(CSV_HEADER + row))

        assert frame.loc[0, "fee"] == 0
        assert frame.loc[0, "tax"] == 0
        assert pd.api.types.is_numeric_dtype(frame["amount"])

    def test_unreadable_numbers_are_rejected_not_zeroed(self, no_isin_lookup):
        row = CSV_ROW.replace(",-1000,", ',"-1.000,50",')
        with pytest.raises(ValueError, match="'amount'"):
            load_data(csv_upload(CSV_HEADER + row))

    def test_utf8_names_are_decoded(self, no_isin_lookup):
        text = CSV_HEADER + CSV_ROW.replace("Apple", "Caf\u00e9 M\u00fcller")
        frame = load_data(FakeUpload(text.encode("utf-8"), "export.csv"))

        assert frame.loc[0, "name"] == "Caf\u00e9 M\u00fcller"

    def test_latin1_files_still_load(self, no_isin_lookup):
        text = CSV_HEADER + CSV_ROW.replace("Apple", "Caf\u00e9")
        frame = load_data(csv_upload(text))

        assert frame.loc[0, "name"] == "Caf\u00e9"

    def test_wrong_files_fail_before_any_ticker_lookup(self, no_isin_lookup):
        with pytest.raises(ValueError, match="Missing required columns"):
            load_data(csv_upload("symbol,foo\nUS0378331005,1\n"))

        assert no_isin_lookup == []

    @pytest.mark.parametrize(
        "column", ["counterparty_iban", "payment_reference", "account_type", "mcc_code"]
    )
    def test_personal_columns_are_dropped(self, column, no_isin_lookup):
        text = (
            CSV_HEADER.rstrip("\n")
            + ",account_type,mcc_code\n"
            + CSV_ROW.rstrip("\n")
            + ",private,1234\n"
        )
        frame = load_data(csv_upload(text))

        assert column not in frame.columns

    def test_dropping_personal_columns_tolerates_their_absence(self, no_isin_lookup):
        text = "date,type,name,symbol,asset_class,shares,amount,currency\n"
        text += "2024-01-05,BUY,Apple,US0378331005,STOCK,10,-1000,EUR\n"
        frame = load_data(csv_upload(text))

        assert len(frame) == 1


class TestLoadDataTickerResolution:
    def test_securities_are_resolved_through_the_isin_lookup(self, no_isin_lookup):
        frame = load_data(csv_upload(CSV_HEADER + CSV_ROW))

        assert frame.loc[0, "ticker"] == "TICK:US0378331005"
        assert no_isin_lookup == ["US0378331005"]

    def test_crypto_rows_skip_the_isin_lookup(self, no_isin_lookup):
        row = CSV_ROW.replace("Apple,US0378331005,STOCK", "Bitcoin,BTC,CRYPTO")
        frame = load_data(csv_upload(CSV_HEADER + row))

        assert frame.loc[0, "ticker"] == "BTC-USD"
        assert no_isin_lookup == []

    def test_mixed_portfolios_use_both_paths(self, no_isin_lookup):
        row = CSV_ROW.replace("Apple,US0378331005,STOCK", "Bitcoin,BTC,CRYPTO")
        frame = load_data(csv_upload(CSV_HEADER + CSV_ROW + row))

        assert frame["ticker"].tolist() == ["TICK:US0378331005", "BTC-USD"]

    def test_each_isin_is_looked_up_once(self, no_isin_lookup):
        frame = load_data(csv_upload(CSV_HEADER + CSV_ROW + CSV_ROW))

        assert no_isin_lookup == ["US0378331005"]
        assert frame["ticker"].tolist() == ["TICK:US0378331005"] * 2

    def test_tickers_given_in_the_file_skip_the_lookup(self, no_isin_lookup):
        text = CSV_HEADER.rstrip("\n") + ",ticker\n" + CSV_ROW.rstrip("\n") + ", aapl \n"
        frame = load_data(csv_upload(text))

        assert frame.loc[0, "ticker"] == "AAPL"
        assert no_isin_lookup == []

    def test_blank_tickers_in_the_file_are_still_resolved(self, no_isin_lookup):
        crypto = CSV_ROW.replace("Apple,US0378331005,STOCK", "Bitcoin,BTC,CRYPTO")
        text = (
            CSV_HEADER.rstrip("\n")
            + ",ticker\n"
            + CSV_ROW.rstrip("\n")
            + ",\n"
            + crypto.rstrip("\n")
            + ",\n"
        )
        frame = load_data(csv_upload(text))

        assert frame["ticker"].tolist() == ["TICK:US0378331005", "BTC-USD"]

    def test_files_without_a_symbol_column_get_no_ticker(self, monkeypatch):
        def fail(isin):
            raise AssertionError("should not look up tickers without symbols")

        monkeypatch.setattr(import_data, "get_ticker_from_isin", fail)
        text = "date,type,name,shares,amount,currency\n"
        text += "2024-01-05,BUY,Apple,10,-1000,EUR\n"
        frame = load_data(csv_upload(text))

        assert frame["ticker"].isna().all()

    def test_missing_optional_columns_get_defaults(self, no_isin_lookup):
        text = "date,type,name,shares,amount,currency\n"
        text += "2024-01-05,BUY,Apple,10,-1000,EUR\n"
        frame = load_data(csv_upload(text))

        assert frame.loc[0, "fee"] == 0
        assert frame.loc[0, "tax"] == 0
        assert {"symbol", "asset_class", "ticker"} <= set(frame.columns)


class TestValidateData:
    def valid_frame(self):
        return pd.DataFrame(
            {
                "date": ["2024-01-05"],
                "type": ["BUY"],
                "name": ["Apple"],
                "shares": [10],
                "amount": [-1000.0],
                "currency": ["EUR"],
            }
        )

    def test_accepts_a_complete_frame(self):
        assert validate_data(self.valid_frame()) is True

    def test_reports_every_missing_column_at_once(self):
        frame = self.valid_frame().drop(columns=["shares", "currency"])

        with pytest.raises(ValueError) as error:
            validate_data(frame)

        assert "shares" in str(error.value)
        assert "currency" in str(error.value)

    def test_rejects_a_file_without_rows(self):
        with pytest.raises(ValueError, match="does not contain any rows"):
            validate_data(self.valid_frame().iloc[0:0])

    def test_rejects_an_unparseable_date_column(self):
        frame = self.valid_frame()
        frame["date"] = ["definitely not a date"]

        with pytest.raises(ValueError, match="Invalid date format"):
            validate_data(frame)

    def test_rejects_dates_that_load_data_turned_into_nat(self):
        frame = self.valid_frame()
        frame["date"] = pd.to_datetime(["not a date"], errors="coerce")

        with pytest.raises(ValueError, match="Invalid date format"):
            validate_data(frame)

    def test_accepts_dates_already_converted_by_load_data(self):
        frame = self.valid_frame()
        frame["date"] = pd.to_datetime(frame["date"])

        assert validate_data(frame) is True


class TestCheckIfDataLoaded:
    def test_passes_when_a_frame_is_in_session_state(self, monkeypatch):
        monkeypatch.setattr(st, "session_state", {"df": pd.DataFrame({"a": [1]})})

        assert check_if_data_loaded() is None

    def test_stops_when_nothing_has_been_uploaded(self, monkeypatch):
        monkeypatch.setattr(st, "session_state", {})

        with pytest.raises(StreamlitStop):
            check_if_data_loaded()
