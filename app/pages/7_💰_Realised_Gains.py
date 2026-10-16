import pandas as pd
import plotly.express as px
import streamlit as st
from utils.chart import NEGATIVE, POSITIVE, show_chart
from utils.import_data import check_if_data_loaded, validate_data
from utils.metrics import calculate_realised_trades
from utils.styling import setup_page

setup_page("Realised gains", "💰")

check_if_data_loaded()
df = st.session_state["df"]
validate_data(df)
trades = df[df["type"].isin(["BUY", "SELL"])].dropna(subset=["date"])
realised = calculate_realised_trades(trades)

if realised.empty:
    st.info("No sell transactions were found in the currently loaded export.")
    st.stop()


def bought_label(sale):
    """One date for a sell matched to one buy day, a range when it spans several."""
    if pd.isna(sale["first_buy_date"]):
        return "Not in export"
    first, last = sale["first_buy_date"], sale["last_buy_date"]
    if first.date() == last.date():
        return f"{first:%d.%m.%Y}"
    return f"{first:%d.%m.%Y} – {last:%d.%m.%Y}"


def pl_colour(value):
    if pd.isna(value) or value == 0:
        return ""
    return f"color: {POSITIVE if value > 0 else NEGATIVE}"


# ---------------------------------------------------------
# FILTERS
# ---------------------------------------------------------
header_left, year_col, asset_col = st.columns([2, 1, 1.5], vertical_alignment="bottom")
with year_col:
    st.caption("YEAR")
    years = sorted(realised["sell_date"].dt.year.unique(), reverse=True)
    selected_year = st.selectbox("Year", ["All years", *years], label_visibility="collapsed")
with asset_col:
    st.caption("ASSETS")
    selected_assets = st.multiselect(
        "Assets",
        sorted(realised["name"].dropna().unique()),
        placeholder="All assets",
        label_visibility="collapsed",
    )

filtered = realised
if selected_year != "All years":
    filtered = filtered[filtered["sell_date"].dt.year == selected_year]
if selected_assets:
    filtered = filtered[filtered["name"].isin(selected_assets)]

if filtered.empty:
    st.warning("No sells were found for the selected filters.")
    st.stop()

# Sells without matching buys in the export have no P/L and are left out of the totals.
matched = filtered.dropna(subset=["profit_loss"])

# ---------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------
pl_after_tax = matched["profit_loss_after_tax"].sum()
pl_before_tax = matched["profit_loss"].sum()
cost_basis = matched["cost_basis"].sum()
taxes = filtered["tax"].sum()
winners = int((matched["profit_loss_after_tax"] > 0).sum())
win_rate = winners / len(matched) if len(matched) else 0

st.markdown('<div class="section-label">REALISED SUMMARY</div>', unsafe_allow_html=True)
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric(
        "Realised P/L (after tax)",
        f"€{pl_after_tax:,.2f}",
        delta=f"{pl_after_tax / cost_basis:+.1%} on cost" if cost_basis else None,
    )
with col2:
    st.metric("Realised P/L (before tax)", f"€{pl_before_tax:,.2f}")
with col3:
    st.metric("Taxes withheld", f"€{taxes:,.2f}")
with col4:
    st.metric("Sells", len(filtered))
with col5:
    st.metric("Win rate", f"{win_rate:.0%}", delta=f"{winners} of {len(matched)} in profit")

# ---------------------------------------------------------
# CHARTS
# ---------------------------------------------------------

left_column, right_column = st.columns(2)

with left_column, st.container(border=True):
    # A single year reads best by month; all years together by year.
    if selected_year == "All years":
        st.markdown("### Realised P/L by year")
        period = matched["sell_date"].dt.year.astype(str)
    else:
        st.markdown("### Realised P/L by month")
        period = matched["sell_date"].dt.strftime("%Y-%m")
    st.caption("Profit or loss after tax, booked on the sell date.")

    by_period = (
        matched.groupby(period)["profit_loss_after_tax"].sum().rename_axis("period").reset_index()
    )
    by_period["result"] = (
        by_period["profit_loss_after_tax"].ge(0).map({True: "Gain", False: "Loss"})
    )
    figure = px.bar(
        by_period,
        x="period",
        y="profit_loss_after_tax",
        color="result",
        color_discrete_map={"Gain": POSITIVE, "Loss": NEGATIVE},
        labels={"period": "", "profit_loss_after_tax": "Realised P/L (€)"},
    )
    figure.update_traces(hovertemplate="%{x}: €%{y:,.2f}<extra></extra>")
    figure.update_layout(showlegend=False)
    figure.update_xaxes(type="category")
    figure.update_yaxes(tickprefix="€", tickformat=",.0f")
    show_chart(figure, height=380)

with right_column, st.container(border=True):
    st.markdown("### Realised P/L by asset")
    st.caption("Assets ranked by their total profit or loss after tax.")

    by_asset = (
        matched.groupby("name", as_index=False)["profit_loss_after_tax"]
        .sum()
        .sort_values("profit_loss_after_tax")
    )
    by_asset["result"] = by_asset["profit_loss_after_tax"].ge(0).map({True: "Gain", False: "Loss"})
    figure = px.bar(
        by_asset,
        x="profit_loss_after_tax",
        y="name",
        orientation="h",
        color="result",
        color_discrete_map={"Gain": POSITIVE, "Loss": NEGATIVE},
        labels={"name": "", "profit_loss_after_tax": "Realised P/L (€)"},
    )
    figure.update_traces(hovertemplate="%{y}: €%{x:,.2f}<extra></extra>")
    figure.update_layout(showlegend=False)
    figure.update_xaxes(tickprefix="€", tickformat=",.0f")
    show_chart(figure, height=380)

# ---------------------------------------------------------
# CLOSED TRADES TABLE
# ---------------------------------------------------------
st.subheader(f"Closed trades ({len(filtered):,})")

table = filtered.sort_values("sell_date", ascending=False).copy()
table["bought"] = table.apply(bought_label, axis=1)
table["return_pct"] = table["return_pct"] * 100
table = table[
    [
        "name",
        "bought",
        "sell_date",
        "shares",
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
]
pl_columns = ["profit_loss", "profit_loss_after_tax", "return_pct"]
st.dataframe(
    table.style.map(pl_colour, subset=pl_columns),
    width="stretch",
    hide_index=True,
    column_config={
        "name": st.column_config.TextColumn("Asset"),
        "bought": st.column_config.TextColumn(
            "Bought", help="Date of the buy, or the range of buys this sell was matched to."
        ),
        "sell_date": st.column_config.DateColumn("Sold", format="DD.MM.YYYY"),
        "shares": st.column_config.NumberColumn("Shares", format="%.4f"),
        "buy_price": st.column_config.NumberColumn(
            "Buy price", format="€%.2f", help="Cost per share of the matched buys, incl. fees."
        ),
        "sell_price": st.column_config.NumberColumn("Sell price", format="€%.2f"),
        "cost_basis": st.column_config.NumberColumn("Cost basis", format="€%.2f"),
        "gross_proceeds": st.column_config.NumberColumn("Proceeds", format="€%.2f"),
        "fee": st.column_config.NumberColumn("Fee", format="€%.2f"),
        "tax": st.column_config.NumberColumn("Tax", format="€%.2f"),
        "profit_loss": st.column_config.NumberColumn("P/L before tax", format="€%.2f"),
        "profit_loss_after_tax": st.column_config.NumberColumn("P/L after tax", format="€%.2f"),
        "return_pct": st.column_config.NumberColumn("Return", format="%+.1f%%"),
        "holding_days": st.column_config.NumberColumn(
            "Held (days)", format="%d", help="Days since the first matched buy."
        ),
    },
)

unmatched = filtered[filtered["unmatched_shares"] > 0]
if not unmatched.empty:
    st.caption(
        f"⚠️ {len(unmatched)} sell(s) include shares bought before the export starts. "
        "Their cost is unknown, so their P/L is overstated or missing."
    )
