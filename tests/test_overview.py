import numpy as np
import pandas as pd
import pytest
from utils.overview import (
    activity_label,
    allocation_by_class,
    cash_balance,
    holdings_timeline,
    invested_capital_timeline,
    market_value_timeline,
    net_invested,
    period_start,
    total_invested,
)


def make_trades(rows):
    """Trades as (date, type, ticker, shares, amount, fee)."""
    trades = pd.DataFrame(rows, columns=["date", "type", "ticker", "shares", "amount", "fee"])
    trades["date"] = pd.to_datetime(trades["date"])
    trades["tax"] = 0.0
    return trades


TRADES = make_trades(
    [
        ("2024-01-01", "BUY", "AAA", 2.0, -100.0, -1.0),
        ("2024-01-03", "BUY", "BBB", 1.0, -50.0, -1.0),
        ("2024-01-04", "SELL", "AAA", 1.0, 70.0, -1.0),
    ]
)


def test_invested_capital_includes_fees_and_nets_out_sales():
    invested = invested_capital_timeline(TRADES)

    assert invested[pd.Timestamp("2024-01-01")] == 101.0
    assert invested[pd.Timestamp("2024-01-02")] == 101.0  # days without trades carry forward
    assert invested[pd.Timestamp("2024-01-03")] == 152.0
    assert invested.iloc[-1] == 152.0 - 69.0


def test_invested_capital_extends_to_end_date():
    invested = invested_capital_timeline(TRADES, end_date="2024-01-10")

    assert invested.index[-1] == pd.Timestamp("2024-01-10")
    assert invested.iloc[-1] == 83.0


def test_holdings_follow_buys_and_sells():
    days = pd.date_range("2024-01-01", "2024-01-04")
    holdings = holdings_timeline(TRADES, days)

    assert holdings["AAA"].tolist() == [2.0, 2.0, 2.0, 1.0]
    assert holdings["BBB"].tolist() == [0.0, 0.0, 1.0, 1.0]


def test_holdings_ignore_sales_beyond_what_was_bought():
    trades = make_trades(
        [
            ("2024-01-01", "SELL", "AAA", 5.0, 500.0, 0.0),
            ("2024-01-02", "BUY", "AAA", 2.0, -200.0, 0.0),
        ]
    )
    holdings = holdings_timeline(trades, pd.date_range("2024-01-01", "2024-01-02"))

    # The later buy must count in full, not be absorbed by the oversold shares.
    assert holdings["AAA"].tolist() == [0.0, 2.0]


def test_market_value_forward_fills_prices_over_weekends():
    days = pd.date_range("2024-01-01", "2024-01-04")
    holdings = holdings_timeline(TRADES, days)
    prices = pd.DataFrame(
        {"AAA": [50.0, np.nan, 55.0, 60.0], "BBB": [np.nan, np.nan, 40.0, 45.0]},
        index=days,
    )

    value = market_value_timeline(holdings, prices)

    assert value.tolist() == [100.0, 100.0, 150.0, 105.0]


def test_market_value_is_hidden_when_a_held_ticker_has_no_prices():
    days = pd.date_range("2024-01-01", "2024-01-04")
    holdings = holdings_timeline(TRADES, days)
    prices = pd.DataFrame({"AAA": [50.0] * 4}, index=days)

    assert market_value_timeline(holdings, prices) is None


def test_allocation_groups_classes_and_appends_cash():
    positions = pd.DataFrame(
        {
            "asset_class": ["STOCK", "FUND", "STOCK", "CRYPTO"],
            "value": [100.0, 250.0, 50.0, 0.0],
        }
    )

    allocation = allocation_by_class(positions, cash_balance=100.0)

    assert allocation["label"].tolist() == ["ETFs", "Stocks", "Cash"]
    assert allocation["share"].tolist() == pytest.approx([0.5, 0.3, 0.2])


def test_allocation_skips_negative_cash():
    positions = pd.DataFrame({"asset_class": ["STOCK"], "value": [100.0]})

    allocation = allocation_by_class(positions, cash_balance=-20.0)

    assert allocation["label"].tolist() == ["Stocks"]


def test_period_start_never_precedes_the_data():
    earliest, latest = pd.Timestamp("2024-06-15"), pd.Timestamp("2024-09-30")

    assert period_start("1M", earliest, latest) == pd.Timestamp("2024-08-30")
    assert period_start("1Y", earliest, latest) == earliest
    assert period_start("All", earliest, latest) == earliest


@pytest.mark.parametrize(
    ("transaction_type", "description", "expected"),
    [
        ("BUY", "Savings plan execution", "Savings plan"),
        ("BUY", "Market order", "Buy"),
        ("DIVIDEND", "", "Dividend"),
        ("TRANSFER_INSTANT_INBOUND", "", "Deposit"),
        ("CARD_TRANSACTION", "", "Transfer"),
    ],
)
def test_activity_label(transaction_type, description, expected):
    transaction = pd.Series({"type": transaction_type, "description": description})

    assert activity_label(transaction) == expected


def test_net_invested_counts_fees_and_taxes():
    trades = make_trades(
        [
            ("2024-01-01", "BUY", "AAA", 1.0, -350.0, -0.99),
            ("2024-02-01", "SELL", "AAA", 1.0, 1000.0, -1.0),
        ]
    )
    trades.loc[1, "tax"] = -50.0

    assert net_invested(trades).tolist() == [350.99, -949.0]
    assert total_invested(trades) == pytest.approx(350.99 - 949.0)


def test_cash_balance_sums_every_cash_movement():
    transactions = pd.DataFrame(
        {
            "amount": [1000.0, -350.0, 12.0, -40.0],
            "fee": [0.0, -1.0, 0.0, 0.0],
            "tax": [0.0, 0.0, -3.0, 0.0],
        }
    )

    assert cash_balance(transactions) == pytest.approx(618.0)
