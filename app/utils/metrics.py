import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
from utils.analysis import load_ticker_info


def get_trades_transactions(df):
    trades_transactions = df[df["type"].isin(["BUY", "SELL"])].copy()
    if trades_transactions.empty:
        st.info("No buy transactions found. Allocation cannot be calculated.")
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

        try:
            yahoo_ticker = yf.Ticker(ticker)
            history = yahoo_ticker.history(period="5d", interval="15m", auto_adjust=False)
            if not history.empty:
                price = history["Close"].dropna().iloc[-1]

            currency = yahoo_ticker.fast_info.get("currency")
            if currency == "USD":
                price_eur = convert_usd_to_eur(price, exchange_rate)
            elif currency == "EUR":
                price_eur = float(price)

            prices[ticker] = price_eur
        except Exception:
            prices[ticker] = np.nan

    return prices


def calculate_positions(trades):
    """
    Calculate current positions and realised P/L using average-cost accounting.

    Buy:
        adds shares and purchase cost (trade amount + fees + taxes)

    Sell:
        reduces open shares and removes the proportional average cost basis.
        realised P/L = net sale proceeds - removed cost basis
    """
    positions = []

    group_columns = ["name", "symbol", "asset_class", "ticker"]

    for asset, asset_trades in trades.groupby(group_columns, dropna=False):
        name, symbol, asset_class, ticker = asset
        asset_trades = asset_trades.sort_values("date")

        open_shares = 0.0
        open_cost_basis = 0.0
        realised_profit_loss = 0.0
        total_purchase_cost = 0.0
        total_sale_proceeds = 0.0

        for _, trade in asset_trades.iterrows():
            shares = abs(trade["shares"])
            fees_and_taxes = abs(trade["fee"]) + abs(trade["tax"])

            if trade["type"] == "BUY":
                # `amount` is negative for buys in this export.
                purchase_cost = abs(trade["amount"]) + fees_and_taxes

                open_shares += shares
                open_cost_basis += purchase_cost
                total_purchase_cost += purchase_cost

            elif trade["type"] == "SELL":
                # `amount` is positive for sells; fees and taxes are negative.
                net_sale_proceeds = abs(trade["amount"]) - fees_and_taxes
                total_sale_proceeds += net_sale_proceeds

                if open_shares <= 0:
                    continue

                # Protect against an export containing a sale larger than holdings.
                shares_sold = min(shares, open_shares)

                average_cost_before_sale = open_cost_basis / open_shares
                removed_cost_basis = shares_sold * average_cost_before_sale

                open_shares -= shares_sold
                open_cost_basis -= removed_cost_basis
                realised_profit_loss += net_sale_proceeds - removed_cost_basis

        # Avoid tiny floating-point leftovers
        if abs(open_shares) < 1e-10:
            open_shares = 0.0

        if abs(open_cost_basis) < 1e-10:
            open_cost_basis = 0.0

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
                "total_purchase_cost": total_purchase_cost,
                "total_sale_proceeds": total_sale_proceeds,
                "realised_profit_loss": realised_profit_loss,
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
