import pandas as pd
import streamlit as st
from utils.ticker_lookup import get_crypto_ticker, get_ticker_from_isin

REQUIRED_COLUMNS = ["date", "type", "name", "shares", "amount", "currency"]
NUMERIC_COLUMNS = ["amount", "fee", "tax", "price", "shares", "quantity", "fy_rate"]
# Columns the pages read but older or trimmed exports may lack.
OPTIONAL_DEFAULTS = {"fee": 0.0, "tax": 0.0, "price": 0.0, "symbol": None, "asset_class": None}
# Cell values that mean "no number" and may safely become 0.
EMPTY_MARKERS = {"", "-", "n/a", "na", "nan", "none", "null"}


def _read_csv(uploaded_file):
    """Read a CSV as UTF-8 (what Trade Republic exports), falling back to Latin-1."""
    try:
        return pd.read_csv(uploaded_file, encoding="utf-8-sig", sep=None, engine="python")
    except UnicodeDecodeError:
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)
        return pd.read_csv(uploaded_file, encoding="ISO-8859-1", sep=None, engine="python")


def _to_numeric(column):
    """Convert a column to numbers; blanks become 0, anything else unreadable raises."""
    numbers = pd.to_numeric(column, errors="coerce")
    text = column.astype(str).str.strip()
    unreadable = numbers.isna() & column.notna() & ~text.str.lower().isin(EMPTY_MARKERS)
    if unreadable.any():
        examples = ", ".join(text[unreadable].unique()[:3])
        raise ValueError(
            f"Column '{column.name}' has {int(unreadable.sum())} values that are not "
            f"numbers (e.g. {examples}). Export with '.' as the decimal separator."
        )
    return numbers.fillna(0)


def _check_required_columns(df):
    missing_columns = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")


def load_data(uploaded_file):
    file_name = uploaded_file.name.lower()

    if file_name.endswith((".csv", ".txt")):
        df = _read_csv(uploaded_file)
    elif file_name.endswith((".xls", ".xlsx")):
        df = pd.read_excel(uploaded_file)
    else:
        raise ValueError("Unsupported file type")

    # Fail on a wrong file before spending time on the ticker lookups below.
    _check_required_columns(df)

    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    for column, default in OPTIONAL_DEFAULTS.items():
        if column not in df.columns:
            df[column] = default

    for column in NUMERIC_COLUMNS:
        if column in df.columns:
            df[column] = _to_numeric(df[column])

    if "month" not in df.columns:
        df["month"] = df["date"].dt.to_period("M").astype(str)

    columns_to_drop = ["account_type", "counterparty_iban", "payment_reference", "mcc_code"]
    df = df.drop(columns=columns_to_drop, errors="ignore")

    is_crypto = df["asset_class"].astype(str).str.strip().str.upper().eq("CRYPTO")

    # A ticker given in the file wins; only the missing ones are derived or looked up.
    df["ticker"] = _given_tickers(df)
    needs_ticker = df["ticker"].isna()

    # Crypto tickers go directly into the shared `ticker` column.
    crypto_rows = is_crypto & needs_ticker
    df.loc[crypto_rows, "ticker"] = df.loc[crypto_rows].apply(
        get_crypto_ticker,
        axis=1,
    )

    # Only securities need the ISIN → ticker lookup.
    security_rows = ~is_crypto & needs_ticker
    unique_isins = df.loc[security_rows, "symbol"].dropna().unique()

    if len(unique_isins):
        with st.spinner("Looking up ticker symbols..."):
            isin_map = {isin: get_ticker_from_isin(isin) for isin in unique_isins}
        df.loc[security_rows, "ticker"] = df.loc[security_rows, "symbol"].map(isin_map)
    return df


def _given_tickers(df):
    """Yahoo Finance tickers already in the file, upper-cased; None where there is none."""
    if "ticker" not in df.columns:
        return pd.Series(None, index=df.index, dtype=object)
    tickers = df["ticker"].astype("string").str.strip().str.upper()
    return tickers.astype(object).where(tickers.notna() & tickers.ne(""), None)


def validate_data(df):
    _check_required_columns(df)

    # Check for empty DataFrame
    if df.empty:
        raise ValueError("The uploaded file does not contain any rows.")

    # load_data turns unreadable dates into NaT, so look for those as well as
    # values that still fail to parse.
    dates = pd.to_datetime(df["date"], errors="coerce")
    invalid_dates = int(dates.isna().sum())
    if invalid_dates:
        raise ValueError(
            f"Invalid date format in the 'date' column ({invalid_dates} rows unreadable)."
        )

    return True


def check_if_data_loaded():
    if st.session_state.get("df") is None:
        st.warning("Please upload a file on the main page first.")
        st.stop()
