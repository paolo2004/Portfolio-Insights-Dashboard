import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from utils.data_source import import_dialog
from utils.import_data import check_if_data_loaded, validate_data
from utils.metrics import calculate_positions, get_trades_transactions
from utils.overview import (
    activity_label,
    allocation_by_class,
    cash_balance,
    get_price_history,
    holdings_timeline,
    invested_capital_timeline,
    market_value_timeline,
    net_cash_flow,
    period_start,
)
from utils.styling import setup_page

ACCENT = "#42dca1"
MARKET_VALUE = "#8a96a8"
SLICE_COLORS = {"ETFs": "#42dca1", "Stocks": "#73a8fa", "Crypto": "#bea0ff", "Cash": "#435165"}
EXTRA_SLICE_COLORS = ["#f2b857", "#ff9d7a", "#7fd4e8"]
TAG_CLASSES = {
    "Buy": "tag-buy",
    "Savings plan": "tag-plan",
    "Sell": "tag-sell",
    "Dividend": "tag-dividend",
    "Interest": "tag-dividend",
    "Deposit": "tag-neutral",
    "Transfer": "tag-neutral",
}
# theme=None lets the app-wide Plotly template apply instead of Streamlit's chart theme.
CHART_OPTIONS = {"width": "stretch", "theme": None, "config": {"displayModeBar": False}}
# Streamlit still injects its own background colour, so set it on each figure.
TRANSPARENT = {"paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)"}


def eur(value, signed=False):
    sign = "+" if signed and value > 0 else "−" if value < 0 else ""
    return f"{sign}€{abs(value):,.2f}"


def kpi_card(label, value, context, tone=""):
    return (
        f'<div class="kpi-card"><div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'<div class="kpi-context {tone}">{context}</div></div>'
    )


def share_label(share):
    """Percent of the portfolio; a sliver like a small cash balance reads "<1%", not "0%"."""
    return "<1%" if 0 < share < 0.005 else f"{share:.0%}"


def initials(name):
    words = [word for word in name.replace("-", " ").split() if word[0].isalnum()]
    return "".join(word[0] for word in words[:2]).upper() or "·"


setup_page("Overview", ":material/dashboard:")
check_if_data_loaded()
df = st.session_state["df"].copy()
validate_data(df)
df = df.dropna(subset=["date"]).sort_values("date")
earliest_date, latest_date = df["date"].min(), df["date"].max()

# ---------------------------------------------------------------- header
# The controls sit in a horizontal container at their natural width, so they
# never squeeze or wrap their labels on mid-sized screens.
heading, controls = st.columns([1, 1.2], vertical_alignment="center")
with (
    controls,
    st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center"),
):
    period = (
        st.segmented_control(
            "Period",
            ["1M", "6M", "1Y", "All"],
            default="All",
            key="overview_period",
            label_visibility="collapsed",
            width="content",
        )
        or "All"
    )
    if st.button("Import CSV", type="primary", icon=":material/upload:", width="content"):
        import_dialog()

start = period_start(period, earliest_date, latest_date)
with heading:
    st.markdown(
        '<div class="dashboard-heading">'
        f'<div class="eyebrow">{start:%b %Y} – {latest_date:%b %Y}</div>'
        "<h1>Overview</h1></div>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------- data
trades = get_trades_transactions(df)
positions = calculate_positions(trades)
open_positions = positions.loc[positions["open_shares"] > 1e-10].copy()
if open_positions.empty:
    st.info("There are no open positions after accounting for sell orders.")
    st.stop()

tickers = tuple(sorted(trades["ticker"].dropna().unique()))
with st.spinner("Loading market prices..."):
    prices = get_price_history(tickers, f"{earliest_date:%Y-%m-%d}") if tickers else pd.DataFrame()

invested = invested_capital_timeline(trades, end_date=latest_date)
market_value = None
if open_positions["ticker"].notna().all():
    market_value = market_value_timeline(holdings_timeline(trades, invested.index), prices)

# Current value per position: latest close where there is one, cost basis otherwise.
latest_prices = prices.ffill().iloc[-1] if not prices.empty else pd.Series(dtype=float)
open_positions["price"] = open_positions["ticker"].map(latest_prices)
open_positions["value"] = (open_positions["open_shares"] * open_positions["price"]).fillna(
    open_positions["open_cost_basis"]
)
unpriced_positions = int(open_positions["price"].isna().sum())

in_period = df.loc[df["date"] >= start]
dividends = df.loc[df["type"] == "DIVIDEND"]
period_dividends = net_cash_flow(dividends.loc[dividends["date"] >= start]).sum()
trailing_dividends = net_cash_flow(
    dividends.loc[dividends["date"] > latest_date - pd.DateOffset(years=1)]
).sum()
cost_basis = open_positions["open_cost_basis"].sum()
cash = cash_balance(df)
holdings_value = open_positions["value"].sum()
portfolio_value = holdings_value + max(cash, 0)
unrealised = holdings_value - cost_basis
months_in_period = max((latest_date - start).days / 30.44, 1)
asset_classes = open_positions["asset_class"].nunique()

# ---------------------------------------------------------------- KPIs
if trailing_dividends > 0 and cost_basis > 0:
    dividend_context, dividend_tone = (
        f"+{trailing_dividends / cost_basis:.1%} yield on cost (12m)",
        "positive",
    )
else:
    dividend_context, dividend_tone = "No dividends in the last 12 months", ""

if unpriced_positions == len(open_positions):
    value_context, value_tone = "No prices available, valued at cost", ""
else:
    change = unrealised / cost_basis if cost_basis else 0
    value_context = f"{eur(unrealised, signed=True)} ({change:+.1%}) unrealised"
    value_tone = "positive" if unrealised >= 0 else "negative"
    if unpriced_positions:
        value_context += f" · {unpriced_positions} at cost"

if cash >= 0:
    cash_context, cash_tone = f"Uninvested on {latest_date:%d %b %Y}", ""
else:
    # A negative balance is impossible on the account itself, so the export is partial.
    cash_context, cash_tone = "Export may not start at account opening", "negative"

st.markdown(
    '<div class="kpi-grid">'
    + kpi_card("Portfolio value", eur(portfolio_value), value_context, value_tone)
    + kpi_card("Cash", eur(cash), cash_context, cash_tone)
    + kpi_card("Dividends received", eur(period_dividends), dividend_context, dividend_tone)
    + kpi_card(
        "Assets held",
        f"{len(open_positions)}",
        f"Across {asset_classes} asset class{'es' if asset_classes != 1 else ''}",
    )
    + kpi_card(
        "Transactions",
        f"{len(in_period):,}",
        f"≈ {len(in_period) / months_in_period:.0f} per month",
    )
    + "</div>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------- chart + allocation
chart_col, allocation_col = st.columns([1.85, 1], gap="medium")

with chart_col, st.container(border=True, key="invested_card", height="stretch"):
    legend = f'<span class="legend-item"><i style="background:{ACCENT}"></i>Invested</span>'
    if market_value is not None:
        legend += (
            '<span class="legend-item">'
            f'<i class="dashed" style="border-color:{MARKET_VALUE}"></i>Market value</span>'
        )
    st.markdown(
        '<div class="card-header"><h3>Invested capital</h3>'
        f'<div class="legend">{legend}</div></div>',
        unsafe_allow_html=True,
    )

    window = invested.loc[invested.index >= start.normalize()]
    # Draw the invested line through the days it changed, so monthly savings plans
    # read as a trend instead of a staircase.
    changed = window.diff().fillna(1).ne(0)
    changed.iloc[-1] = True
    invested_points = window[changed]
    figure = go.Figure()
    if market_value is not None:
        figure.add_trace(
            go.Scatter(
                x=window.index,
                y=market_value.reindex(window.index),
                name="Market value",
                mode="lines",
                line=dict(color=MARKET_VALUE, width=1.4, dash="dot"),
                hovertemplate="€%{y:,.2f}<extra>Market value</extra>",
            )
        )
    figure.add_trace(
        go.Scatter(
            x=invested_points.index,
            y=invested_points,
            name="Invested",
            mode="lines",
            line=dict(color=ACCENT, width=2.2),
            fill="tozeroy",
            fillgradient=dict(
                type="vertical",
                colorscale=[[0, "rgba(66,220,161,0)"], [1, "rgba(66,220,161,.28)"]],
            ),
            hovertemplate="€%{y:,.2f}<extra>Invested</extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[window.index[-1]],
            y=[window.iloc[-1]],
            mode="markers",
            marker=dict(color=ACCENT, size=8, line=dict(color="#121923", width=2)),
            hoverinfo="skip",
        )
    )
    figure.update_layout(
        **TRANSPARENT,
        height=300,
        showlegend=False,
        hovermode="x unified",
        margin=dict(l=0, r=8, t=8, b=0),
    )
    figure.update_xaxes(tickformat="%b %y", nticks=6, showline=False)
    figure.update_yaxes(tickprefix="€", tickformat="~s", nticks=4, rangemode="tozero")
    st.plotly_chart(figure, **CHART_OPTIONS)

    if market_value is None:
        st.caption(
            "Market value is hidden because price history is missing for at least one held asset."
        )

with allocation_col, st.container(border=True, key="allocation_card", height="stretch"):
    title_col, link_col = st.columns([1, 0.45], vertical_alignment="center")
    title_col.markdown("<h3 class='card-title'>Allocation</h3>", unsafe_allow_html=True)
    link_col.page_link("pages/2_🥧_Allocation.py", label="Details")

    allocation = allocation_by_class(open_positions, cash)
    extra_colors = iter(EXTRA_SLICE_COLORS * 3)
    allocation["color"] = [
        SLICE_COLORS.get(label) or next(extra_colors) for label in allocation["label"]
    ]

    donut_col, legend_col = st.columns([1, 1.25], vertical_alignment="center")
    with donut_col:
        donut = go.Figure(
            go.Pie(
                labels=allocation["label"],
                values=allocation["value"],
                hole=0.72,
                sort=False,
                direction="clockwise",
                marker=dict(colors=allocation["color"], line=dict(color="#121923", width=3)),
                textinfo="none",
                hovertemplate="%{label}<br>€%{value:,.2f} · %{percent}<extra></extra>",
            )
        )
        donut.update_layout(
            **TRANSPARENT, height=150, showlegend=False, margin=dict(l=0, r=0, t=0, b=0)
        )
        st.plotly_chart(donut, **CHART_OPTIONS)
    with legend_col:
        items = "".join(
            f'<li><i style="background:{row.color}"></i>{html.escape(row.label)}'
            f"<span>{share_label(row.share)}</span></li>"
            for row in allocation.itertuples()
        )
        st.markdown(f'<ul class="allocation-legend">{items}</ul>', unsafe_allow_html=True)

    largest = open_positions.loc[open_positions["value"].idxmax(), "name"]
    note = f"Largest position: <strong>{html.escape(str(largest))}</strong>"
    if unpriced_positions:
        note += (
            f'<br><span class="muted">{unpriced_positions} without a price, valued at cost</span>'
        )
    st.markdown(f'<div class="card-footer">{note}</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------- recent activity
with st.container(border=True, key="recent_card"):
    title_col, link_col = st.columns([1, 0.3], vertical_alignment="center")
    title_col.markdown("<h3 class='card-title'>Recent activity</h3>", unsafe_allow_html=True)
    link_col.page_link("pages/4_🔁_Transactions.py", label="View all transactions")

    sort_column = "datetime" if "datetime" in df.columns else "date"
    rows = []
    for _, transaction in df.sort_values(sort_column, ascending=False).head(6).iterrows():
        label = activity_label(transaction)
        if pd.notna(transaction["name"]) and str(transaction["name"]).strip():
            name = str(transaction["name"])
        else:
            name = {"Interest": "Interest on cash", "Deposit": "Cash deposit"}.get(
                label, "Cash account"
            )
        amount = transaction["amount"] + transaction["fee"] + transaction["tax"]
        # Money in gets a sign and the accent colour; money out is shown as a plain amount.
        amount_cell = (
            f'<td class="amount positive">{eur(amount, signed=True)}</td>'
            if amount > 0
            else f'<td class="amount">{eur(abs(amount))}</td>'
        )
        safe_name = html.escape(name)
        rows.append(
            '<tr><td class="asset">'
            f'<span class="asset-initial">{html.escape(initials(name))}</span>{safe_name}</td>'
            f'<td><span class="tag {TAG_CLASSES[label]}">{label}</span></td>'
            f"<td>{transaction['date']:%d %b %Y}</td>{amount_cell}</tr>"
        )

    st.markdown(
        '<table class="activity-table"><thead><tr>'
        "<th>Asset</th><th>Type</th><th>Date</th><th>Amount</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>",
        unsafe_allow_html=True,
    )
