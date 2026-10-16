import os

import requests
import streamlit as st
import yfinance as yf

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
# Exchange codes as OpenFIGI reports them, mapped to Yahoo Finance suffixes.
# Only listings on these exchanges are tried: an unmapped code could resolve
# a bare ticker to an unrelated company that shares the symbol elsewhere.
EXCHANGE_SUFFIXES = {
    "IR": "IR",
    "L": "L",
    "LN": "L",
    "DE": "DE",
    "XET": "DE",
    "GY": "DE",  # Xetra
    "GR": "DE",  # German composite
    "GF": "F",  # Frankfurt
    "GM": "MU",  # Munich
    "GS": "SG",  # Stuttgart
    "GD": "DU",  # Düsseldorf
    "GB": "BE",  # Berlin
    "GH": "HM",  # Hamburg
    "GI": "HA",  # Hanover
    "PA": "PA",
    "FP": "PA",
    "EP": "PA",
    "SW": "SW",
    "AS": "AS",
    "MI": "MI",
    "MC": "MC",
    "OL": "OL",
    "ST": "ST",
    "TO": "TO",
    "AX": "AX",
    "HK": "HK",
    "TW": "TW",
    "BR": "SA",
    "BZ": "SA",
    "CN": "TO",  # Canada composite
    "CG": "SS",  # Shanghai
    "CS": "SZ",  # Shenzhen
    "US": "",
    "UN": "",  # NYSE
    "UW": "",  # Nasdaq Global Select
    "UQ": "",  # Nasdaq Global Market
    "UR": "",  # Nasdaq Capital Market
    "UA": "",  # NYSE American
    "UP": "",  # NYSE Arca
}


def _format_yahoo_symbol(ticker, exch_code):
    """Convert an OpenFIGI ticker into a possible Yahoo Finance symbol."""

    if not ticker:
        return None

    ticker = str(ticker).strip().upper()

    if not ticker:
        return None

    exch_code = str(exch_code or "").strip().upper()

    suffix = EXCHANGE_SUFFIXES.get(exch_code)

    if suffix is None:
        return ticker

    if suffix == "":
        return ticker

    return f"{ticker}.{suffix}"


def _validate_yahoo_ticker(symbol):
    """Check whether a symbol exists on Yahoo Finance."""

    if not symbol:
        return False

    try:
        history = yf.Ticker(symbol).history(period="5d", raise_errors=False)

        return not history.empty

    except Exception:
        return False


def get_ticker_from_isin(isin):
    """
    Convert an ISIN into a Yahoo Finance ticker.
    """

    if not isin or not isinstance(isin, str):
        return None

    isin = isin.strip().upper()
    if not isin:
        return None

    try:
        return _lookup_ticker(isin)
    except Exception:
        # Network errors and rate limits (HTTP 429) land here. They are not
        # cached, so the next import tries again instead of keeping the failure.
        return None


@st.cache_data(show_spinner=False)
def _lookup_ticker(isin):
    """Cached OpenFIGI lookup; raises on network errors so they are not cached."""
    headers = {"Content-Type": "application/json"}
    # An API key raises OpenFIGI's limit from 25 to 250 requests per minute.
    api_key = os.getenv("OPENFIGI_API_KEY")
    if api_key:
        headers["X-OPENFIGI-APIKEY"] = api_key

    payload = [
        {
            "idType": "ID_ISIN",
            "idValue": isin,
        }
    ]

    response = requests.post(
        OPENFIGI_URL,
        json=payload,
        headers=headers,
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()

    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        return None

    for item in data[0].get("data", []):
        ticker = item.get("ticker")
        exch_code = str(item.get("exchCode") or "").strip().upper()
        if not ticker or exch_code not in EXCHANGE_SUFFIXES:
            continue
        symbol = _format_yahoo_symbol(ticker, exch_code)
        if _validate_yahoo_ticker(symbol):
            return symbol

    return None


def get_crypto_ticker(row):
    asset_class = str(row.get("asset_class", "")).strip().upper()
    symbol = str(row.get("symbol", "")).strip().upper()

    if asset_class != "CRYPTO" or not symbol:
        return None

    return f"{symbol}-USD"
