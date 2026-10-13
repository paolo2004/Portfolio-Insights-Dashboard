import numpy as np
import plotly.express as px
import streamlit as st
from utils.chart import CATEGORICAL, show_chart
from utils.import_data import check_if_data_loaded, validate_data
from utils.metrics import (
    add_country_column,
    add_sector_column,
    calculate_country_allocation,
    calculate_sector_allocation,
    get_trades_transactions,
)
from utils.overview import net_invested, total_invested
from utils.styling import setup_page

setup_page("Portfolio Allocation", "🥧")

check_if_data_loaded()
df = st.session_state["df"].copy()
validate_data(df)

trade_transactions = get_trades_transactions(df)

# Use a share-weighted price because buy orders can contain different quantities.
trade_transactions["trade_value"] = trade_transactions["price"] * trade_transactions["shares"]
trade_transactions["net_invested"] = net_invested(trade_transactions)

st.markdown('<div class="section-label">ALLOCATION SUMMARY</div>', unsafe_allow_html=True)

cel1, cel2, cel3 = st.columns(3)
cel1.metric("Total invested", f"€{total_invested(trade_transactions):,.2f}")
cel2.metric("Trade transactions", f"{len(trade_transactions):,}")
cel3.metric("Unique assets", f"{trade_transactions['name'].nunique():,}")

# dropna=False keeps assets whose ticker lookup failed; they still hold invested capital.
allocation_by_asset = trade_transactions.groupby(
    ["name", "asset_class", "ticker"],
    as_index=False,
    dropna=False,
).agg(
    total_invested=("net_invested", "sum"),
    total_shares=("shares", "sum"),
    number_of_trade_transactions=("amount", "count"),
    total_trade_value=("trade_value", "sum"),
    total_fee=("fee", "sum"),
    asset_class=("asset_class", "first"),
)

allocation_by_asset["avg_buy_price"] = np.where(
    allocation_by_asset["total_shares"] != 0,
    allocation_by_asset["total_trade_value"] / allocation_by_asset["total_shares"],
    np.nan,
)

# The sector and country lookups skip a missing ticker only when it is None, not NaN.
allocation_by_asset["ticker"] = allocation_by_asset["ticker"].astype(object)
allocation_by_asset.loc[allocation_by_asset["ticker"].isna(), "ticker"] = None

with st.spinner("Resolving sectors and countries..."):
    allocation_by_asset = add_sector_column(allocation_by_asset)
    allocation_by_asset = add_country_column(allocation_by_asset)

sorted_allocation = allocation_by_asset.sort_values(by="total_invested", ascending=False)

# An asset whose sales returned more than was put in has a negative net invested
# amount. It still counts towards the total, but has no share of the charts.
invested_assets = sorted_allocation.loc[sorted_allocation["total_invested"] > 0]
returned_assets = sorted_allocation.loc[sorted_allocation["total_invested"] <= 0, "name"]
sector_allocation = calculate_sector_allocation(invested_assets)
country_allocation = calculate_country_allocation(invested_assets)


def allocation_bar(data, value_column, label_column, value_title, key, height=350):
    """Sorted horizontal bar - the readable form for many close-valued shares."""
    figure = px.bar(
        data.sort_values(value_column, ascending=True),
        x=value_column,
        y=label_column,
        orientation="h",
        labels={label_column: "", value_column: value_title},
    )
    figure.update_traces(marker_color=CATEGORICAL[0])
    show_chart(figure, height=height, key=key)


col1, col2 = st.columns(2)

with col1:
    with st.container(border=True):
        st.markdown("### Portfolio allocation")
        caption = "Net invested capital per asset, fees and taxes included."
        if not returned_assets.empty:
            caption += (
                f" Not shown: {', '.join(returned_assets)}, "
                "where sales returned more than was invested."
            )
        st.caption(caption)
        allocation_bar(invested_assets, "total_invested", "name", "Invested (€)", "all_assets")

with col2:
    with st.container(border=True):
        st.markdown("### Allocation by asset class")
        asset_class = invested_assets.groupby("asset_class", as_index=False)["total_invested"].sum()
        figure = px.pie(asset_class, names="asset_class", values="total_invested", hole=0.68)
        figure.update_traces(marker=dict(line=dict(color="#10151d", width=2)))
        show_chart(figure)

col1, col2 = st.columns(2)

with col1:
    with st.container(border=True):
        st.markdown("### Stock allocation")

        stock_allocation = invested_assets[invested_assets["asset_class"] == "STOCK"]
        if stock_allocation.empty:
            st.info("No stock transactions found.")
        else:
            allocation_bar(stock_allocation, "total_invested", "name", "Invested (€)", "stocks")

with col2:
    with st.container(border=True):
        st.markdown("### Crypto allocation")

        crypto_allocation = invested_assets[invested_assets["asset_class"] == "CRYPTO"]
        if crypto_allocation.empty:
            st.info("No crypto transactions found.")
        else:
            allocation_bar(crypto_allocation, "total_invested", "name", "Invested (€)", "crypto")

columns = st.columns(2)

with columns[0]:
    with st.container(border=True):
        st.markdown("### Allocation by country")

        country_figure = px.pie(
            country_allocation,
            values="amount",
            names="country",
            hole=0.68,
        )
        country_figure.update_traces(
            marker=dict(line=dict(color="#10151d", width=2)),
        )
        show_chart(country_figure)

with columns[1]:
    with st.container(border=True):
        st.markdown("### Allocation by sector")
        allocation_bar(sector_allocation, "amount", "sector", "Invested (€)", "sectors")

col1, col2 = st.columns(2)
with col1:
    with st.container(border=True):
        st.markdown("### Allocation by asset")
        
        display_columns = [
            "name",
            "total_invested",
            "total_shares",
            "number_of_trade_transactions",
            "sector",
            "country",
        ]
        st.dataframe(
            sorted_allocation[display_columns],
            width="stretch",
            hide_index=True,
            column_config={
                "name": st.column_config.TextColumn("Asset"),
                "total_invested": st.column_config.NumberColumn(
                    "Net invested",
                    format="€%.2f",
                ),
                "total_shares": st.column_config.NumberColumn(
                    "Total shares",
                    format="%.2f",
                ),
                "number_of_trade_transactions": st.column_config.NumberColumn(
                    "Number of trades",
                    format="%d",
                ),
                "sector": st.column_config.TextColumn("Sector"),
                "country": st.column_config.TextColumn("Country"),
            },
        )

with col2:
    with st.container(border=True):
        st.markdown("### Allocation over time")
        st.caption("Net capital invested (+) or taken out through sales (−) on each trading day.")

        allocation_over_time = trade_transactions.groupby("date", as_index=False).agg(
            total_invested=("net_invested", "sum")
        )

        figure = px.line(
            allocation_over_time,
            x="date",
            y="total_invested",
            labels={"date": "", "total_invested": "Invested (€)"},
        )
        figure.update_traces(line_width=2)
        show_chart(figure, height=400)

with st.expander("Show All Transactions"):
    st.dataframe(df, width="stretch", hide_index=True)
