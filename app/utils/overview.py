"""Calculations behind the Overview page.

Everything except `get_price_history` is pure pandas, so it can be tested
without Streamlit or network access.
"""

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

PERIOD_OFFSETS = {
    "1M": pd.DateOffset(months=1),
    "6M": pd.DateOffset(months=6),
    "1Y": pd.DateOffset(years=1),
}

ASSET_CLASS_LABELS = {
    "FUND": "ETFs",
    "ETF": "ETFs",
    "STOCK": "Stocks",
    "CRYPTO": "Crypto",
    "BOND": "Bonds",
    "DERIVATIVE": "Derivatives",
}


def period_start(period, earliest_date, latest_date):
    """Return the first date inside a 1M / 6M / 1Y / All window."""
    if period not in PERIOD_OFFSETS:
        return earliest_date
    return max(latest_date - PERIOD_OFFSETS[period], earliest_date)


def net_cash_flow(transactions):
    """Signed effect of each row on the cash account (amount + fee + tax)."""
    return transactions["amount"] + transactions["fee"] + transactions["tax"]


def net_invested(trades):
    """Capital each trade put into (+) or took out of (-) the portfolio.

    This is the app's single definition of "invested": buys count with their
    fees, sales count with what actually came back after fees and taxes.
    Buys have a negative cash flow and sells a positive one, hence the negation.
    """
    return -net_cash_flow(trades)


def total_invested(trades):
    """Net invested capital across all trades."""
    return net_invested(trades).sum()


def cash_balance(transactions):
    """Uninvested cash: the sum of every cash movement in the export.

    Only correct when the export starts at account opening; a partial export
    misses the earlier movements.
    """
    return net_cash_flow(transactions).sum()


def invested_capital_timeline(trades, end_date=None):
    """Daily running total of `net_invested`, one row per calendar day."""
    if trades.empty:
        return pd.Series(dtype=float)

    daily = net_invested(trades).groupby(trades["date"].dt.normalize()).sum()
    end_date = pd.Timestamp(end_date or daily.index.max()).normalize()
    days = pd.date_range(daily.index.min(), max(end_date, daily.index.max()), freq="D")
    return daily.reindex(days, fill_value=0).cumsum()


def holdings_timeline(trades, days):
    """Shares held per ticker at the end of each day in `days`."""
    if trades.empty:
        return pd.DataFrame(index=days)

    signed_shares = trades["shares"].abs().where(trades["type"] == "BUY", -trades["shares"].abs())
    daily = signed_shares.groupby([trades["date"].dt.normalize(), trades["ticker"]]).sum()
    changes = daily.unstack(fill_value=0).reindex(days, fill_value=0)

    # Selling more than the export shows as bought must not create short positions.
    # Clip the running total at every step (not once at the end), so a later buy
    # starts from zero, the same way `calculate_positions` ignores the excess sale.
    held = np.zeros(changes.shape[1])
    rows = []
    for change in changes.to_numpy():
        held = np.maximum(held + change, 0)
        rows.append(held)
    return pd.DataFrame(rows, index=changes.index, columns=changes.columns)


def market_value_timeline(holdings, prices):
    """Daily market value of the holdings, or None when a held ticker has no prices.

    A partial line would sit below the invested line and look like a loss, so
    the chart shows no market value at all rather than an incomplete one.
    """

    if holdings.empty or holdings.shape[1] == 0:
        return None

    held_tickers = holdings.columns[holdings.gt(0).any()]
    missing = [ticker for ticker in held_tickers if ticker not in prices.columns]
    if missing:
        return None

    aligned = prices.reindex(columns=held_tickers)
    aligned = aligned.reindex(aligned.index.union(holdings.index)).sort_index().ffill()
    aligned = aligned.reindex(holdings.index)

    values = holdings[held_tickers] * aligned
    # Before a ticker's first quote its value is unknown, not zero.
    unknown = aligned.isna() & holdings[held_tickers].gt(0)
    total = values.sum(axis=1)
    total[unknown.any(axis=1)] = np.nan
    return total


def asset_class_label(asset_class):
    if pd.isna(asset_class) or not str(asset_class).strip():
        return "Other"
    key = str(asset_class).strip().upper()
    return ASSET_CLASS_LABELS.get(key, key.title())


def allocation_by_class(positions, cash_balance=0.0):
    """Value per asset class, largest first, with cash as the last slice.

    `positions` needs `asset_class` and `value` columns.
    """
    allocation = (
        positions.assign(label=positions["asset_class"].map(asset_class_label))
        .groupby("label", as_index=False)["value"]
        .sum()
        .sort_values("value", ascending=False)
    )
    allocation = allocation.loc[allocation["value"] > 0]
    if cash_balance > 0:
        cash = pd.DataFrame({"label": ["Cash"], "value": [cash_balance]})
        allocation = pd.concat([allocation, cash], ignore_index=True)

    total = allocation["value"].sum()
    allocation["share"] = allocation["value"] / total if total > 0 else 0.0
    return allocation.reset_index(drop=True)


def activity_label(transaction):
    """Short label for the recent activity table."""
    transaction_type = str(transaction["type"])
    description = str(transaction.get("description", "")).lower()
    if transaction_type == "BUY" and "savings plan" in description:
        return "Savings plan"
    return {
        "BUY": "Buy",
        "SELL": "Sell",
        "DIVIDEND": "Dividend",
        "INTEREST_PAYMENT": "Interest",
    }.get(transaction_type, "Deposit" if "INBOUND" in transaction_type else "Transfer")


def _daily_close(yahoo_ticker, start):
    close = yahoo_ticker.history(start=start, interval="1d", auto_adjust=False)["Close"].dropna()
    close.index = close.index.tz_localize(None).normalize()
    return close.groupby(level=0).last()


def _close_in_eur(ticker, start, usd_to_eur):
    """Daily EUR closes for one ticker, or None when they cannot be determined."""
    try:
        yahoo_ticker = yf.Ticker(ticker)
        close = _daily_close(yahoo_ticker, start)
        currency = yahoo_ticker.fast_info.get("currency")
    except Exception:
        return None

    if close.empty:
        return None
    if currency == "EUR":
        return close
    if currency == "USD" and usd_to_eur is not None:
        return close * usd_to_eur.reindex(close.index, method="ffill")
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def get_price_history(tickers, start):
    """Daily closing prices in EUR, one column per ticker.

    Tickers that fail to download or trade in a currency other than EUR or USD
    are left out; `market_value_timeline` treats them as missing.
    """
    try:
        usd_to_eur = _daily_close(yf.Ticker("USDEUR=X"), start)
    except Exception:
        usd_to_eur = None

    closes = {ticker: _close_in_eur(ticker, start, usd_to_eur) for ticker in tickers}
    return pd.DataFrame({ticker: close for ticker, close in closes.items() if close is not None})
