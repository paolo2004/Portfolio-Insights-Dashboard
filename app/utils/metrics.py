from collections import deque

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
from utils.analysis import load_ticker_info


def get_trades_transactions(df):
    trades_transactions = df[df["type"].isin(["BUY", "SELL"])].copy()
    if trades_transactions.empty:
        st.info("No buy or sell transactions found. Allocation cannot be calculated.")
        st.stop()
    else:
        return trades_transactions


@st.cache_data(ttl=900, show_spinner=False)
def get_usd_eur_rate():
    try:
        ticker = yf.Ticker("USDEUR=X")
        rate = ticker.fast_info.get("last_price")

        if rate is None or pd.isna(rate):
            history = ticker.history(period="5d", interval="15m", auto_adjust=False)

            if not history.empty:
                rate = history["Close"].dropna().iloc[-1]

        if rate is None or pd.isna(rate):
            return np.nan

        return float(rate)

    except Exception:
        return np.nan


def convert_usd_to_eur(price_usd, exchange_rate):
    if price_usd is None:
        return None

    return float(price_usd) * float(exchange_rate)


@st.cache_data(ttl=900, show_spinner=False)
def get_current_prices(tickers):
    """Return latest available Yahoo Finance prices, cached for 15 minutes."""
    prices = {}
    exchange_rate = get_usd_eur_rate()

    for ticker in tickers:
        if not ticker:
            continue

        # Reset per ticker so a missing price never inherits the previous ticker's.
        price_eur = np.nan
        try:
            yahoo_ticker = yf.Ticker(ticker)
            history = yahoo_ticker.history(period="5d", interval="15m", auto_adjust=False)
            closes = history["Close"].dropna() if not history.empty else pd.Series(dtype=float)
            if not closes.empty:
                price = closes.iloc[-1]
                currency = yahoo_ticker.fast_info.get("currency")
                if currency == "USD":
                    price_eur = convert_usd_to_eur(price, exchange_rate)
                elif currency == "EUR":
                    price_eur = float(price)

            prices[ticker] = price_eur
        except Exception:
            prices[ticker] = np.nan

    return prices


ASSET_COLUMNS = ["name", "symbol", "asset_class", "ticker"]
REALISED_COLUMNS = [
    *ASSET_COLUMNS,
    "sell_date",
    "shares",
    "unmatched_shares",
    "first_buy_date",
    "last_buy_date",
    "buy_price",
    "sell_price",
    "cost_basis",
    "gross_proceeds",
    "fee",
    "tax",
    "profit_loss",
    "profit_loss_after_tax",
    "return_pct",
    "holding_days",
]
# Share counts below this are floating-point leftovers, not real holdings.
EPSILON = 1e-10


def _match_fifo(asset_trades):
    """
    Replay one asset's trades in date order, matching every sell against the
    oldest buys still open (FIFO, as German tax law does for securities).

    Returns the realised sales, one dict per sell, and the lots still open.
    Each lot is a dict with the buy `date`, the `shares` left and their `cost`
    (purchase amount + fees + taxes, reduced proportionally by earlier sells).
    """
    lots = deque()
    sales = []

    # A stable sort keeps the export's row order for trades on the same day.
    for _, trade in asset_trades.sort_values("date", kind="stable").iterrows():
        shares = abs(trade["shares"])
        fee = abs(trade["fee"])
        tax = abs(trade["tax"])

        if trade["type"] == "BUY":
            # `amount` is negative for buys in this export.
            lots.append(
                {"date": trade["date"], "shares": shares, "cost": abs(trade["amount"]) + fee + tax}
            )
            continue
        if trade["type"] != "SELL":
            continue

        remaining = shares
        cost_basis = 0.0
        buy_dates = []
        while remaining > EPSILON and lots:
            lot = lots[0]
            taken = min(remaining, lot["shares"])
            taken_cost = lot["cost"] * taken / lot["shares"]

            cost_basis += taken_cost
            buy_dates.append(lot["date"])
            lot["shares"] -= taken
            lot["cost"] -= taken_cost
            remaining -= taken
            if lot["shares"] <= EPSILON:
                lots.popleft()

        matched = shares - remaining
        # `amount` is positive for sells; fees and taxes are negative.
        gross_proceeds = abs(trade["amount"])
        if matched > EPSILON:
            # A sale larger than the holdings in the export keeps its full
            # proceeds but only the matched shares' cost; `unmatched_shares`
            # lets the page flag it.
            profit_loss = gross_proceeds - fee - cost_basis
            profit_loss_after_tax = profit_loss - tax
            first_buy, last_buy = min(buy_dates), max(buy_dates)
            sale = {
                "first_buy_date": first_buy,
                "last_buy_date": last_buy,
                "buy_price": cost_basis / matched,
                "cost_basis": cost_basis,
                "profit_loss": profit_loss,
                "profit_loss_after_tax": profit_loss_after_tax,
                "return_pct": profit_loss_after_tax / cost_basis if cost_basis else np.nan,
                "holding_days": (trade["date"] - first_buy).days,
            }
        else:
            # Nothing bought in the export to match against: no P/L can be computed.
            sale = dict.fromkeys(
                [
                    "first_buy_date",
                    "last_buy_date",
                    "buy_price",
                    "cost_basis",
                    "profit_loss",
                    "profit_loss_after_tax",
                    "return_pct",
                    "holding_days",
                ],
                np.nan,
            )

        sales.append(
            {
                **sale,
                "sell_date": trade["date"],
                "shares": shares,
                "unmatched_shares": remaining if remaining > EPSILON else 0.0,
                "sell_price": gross_proceeds / shares if shares else np.nan,
                "gross_proceeds": gross_proceeds,
                "fee": fee,
                "tax": tax,
            }
        )

    return sales, lots


def calculate_realised_trades(trades):
    """
    One row per sell with its FIFO-matched buys.

    buy_price:  cost per share of the matched buys, including their fees and taxes
    sell_price: gross sale price per share
    profit_loss: gross proceeds - sell fee - cost basis (before tax)
    profit_loss_after_tax: profit_loss - tax withheld on the sale
    """
    rows = []
    for asset, asset_trades in trades.groupby(ASSET_COLUMNS, dropna=False):
        sales, _ = _match_fifo(asset_trades)
        identity = dict(zip(ASSET_COLUMNS, asset, strict=True))
        rows.extend({**identity, **sale} for sale in sales)

    realised = pd.DataFrame(rows, columns=REALISED_COLUMNS)
    return realised.sort_values("sell_date", kind="stable", ignore_index=True)


def calculate_positions(trades):
    """
    Calculate current positions and realised P/L using FIFO accounting.

    Buy:
        opens a lot with its shares and purchase cost (trade amount + fees + taxes)

    Sell:
        consumes the oldest open lots first, removing their cost proportionally.
        realised P/L = net sale proceeds (after fees and taxes) - removed cost basis
    """
    positions = []

    for asset, asset_trades in trades.groupby(ASSET_COLUMNS, dropna=False):
        name, symbol, asset_class, ticker = asset
        sales, lots = _match_fifo(asset_trades)

        open_shares = sum(lot["shares"] for lot in lots)
        open_cost_basis = sum(lot["cost"] for lot in lots)

        # Avoid tiny floating-point leftovers
        if abs(open_shares) < EPSILON:
            open_shares = 0.0

        if abs(open_cost_basis) < EPSILON:
            open_cost_basis = 0.0

        buys = asset_trades[asset_trades["type"] == "BUY"]
        total_purchase_cost = (buys["amount"].abs() + buys["fee"].abs() + buys["tax"].abs()).sum()
        total_sale_proceeds = sum(
            sale["gross_proceeds"] - sale["fee"] - sale["tax"] for sale in sales
        )
        # Sells with nothing to match against have no P/L (NaN) and add nothing.
        realised_profit_loss = sum(
            sale["profit_loss_after_tax"]
            for sale in sales
            if pd.notna(sale["profit_loss_after_tax"])
        )

        avg_cost_per_share = open_cost_basis / open_shares if open_shares > 0 else np.nan
        positions.append(
            {
                "name": name,
                "symbol": symbol,
                "asset_class": asset_class,
                "ticker": ticker,
                "open_shares": open_shares,
                "open_cost_basis": open_cost_basis,
                "avg_cost_per_share": avg_cost_per_share,
                "total_purchase_cost": float(total_purchase_cost),
                "total_sale_proceeds": float(total_sale_proceeds),
                "realised_profit_loss": float(realised_profit_loss),
            }
        )

    return pd.DataFrame(positions)


def get_sector_for_ticker(ticker_symbol, asset_class):
    """Return the sector of an asset from Yahoo Finance."""
    if not ticker_symbol:
        return "Unknown"

    info = load_ticker_info(ticker_symbol)
    sector = info.get("industry")
    if not sector:
        sector = str(asset_class).strip().upper() or "Unknown"

    return sector


def add_sector_column(allocation_data):
    """Add a sector column based on each asset's Yahoo Finance ticker."""
    allocation_data = allocation_data.copy()
    allocation_data["sector"] = allocation_data.apply(
        lambda row: get_sector_for_ticker(
            row["ticker"],
            row["asset_class"],
        ),
        axis=1,
    )
    return allocation_data


def get_country_for_ticker(ticker_symbol, asset_class):
    """Return the country of an asset from Yahoo Finance."""
    if not ticker_symbol:
        return "Unknown"
    if asset_class in ["ETF", "ETC", "ETN", "FUND"] or asset_class == "CRYPTO":
        return "Global"

    info = load_ticker_info(ticker_symbol)
    country = info.get("country", "Unknown")

    return country


def add_country_column(allocation_data):
    """Add a country column based on each asset's Yahoo Finance ticker."""
    allocation_data = allocation_data.copy()
    allocation_data["country"] = allocation_data.apply(
        lambda row: get_country_for_ticker(row["ticker"], row["asset_class"]),
        axis=1,
    )
    return allocation_data


def calculate_sector_allocation(allocation_data):
    """Calculate total invested amount and percentage per sector."""
    sector_allocation = (
        allocation_data.groupby("sector", as_index=False)
        .agg(
            amount=("total_invested", "sum"),
            assets=("name", "nunique"),
        )
        .sort_values("amount", ascending=False)
    )

    total_amount = sector_allocation["amount"].sum()

    sector_allocation["percentage"] = (
        sector_allocation["amount"] / total_amount * 100 if total_amount > 0 else 0
    )

    return sector_allocation


def calculate_country_allocation(allocation_data):
    """Calculate total invested amount and percentage per country."""
    country_allocation = (
        allocation_data.groupby("country", as_index=False)
        .agg(
            amount=("total_invested", "sum"),
            assets=("name", "nunique"),
        )
        .sort_values("amount", ascending=False)
    )

    total_amount = country_allocation["amount"].sum()

    country_allocation["percentage"] = (
        country_allocation["amount"] / total_amount * 100 if total_amount > 0 else 0
    )

    return country_allocation
