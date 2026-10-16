import plotly.express as px
import streamlit as st
from utils.chart import CATEGORICAL, DIVERGING, show_chart
from utils.import_data import (
    check_if_data_loaded,
    validate_data,
)
from utils.styling import setup_page

setup_page("Transactions", "🔁")

check_if_data_loaded()
df = st.session_state["df"].copy()
validate_data(df)

df = df.dropna(subset=["date"]).copy()
df = df.sort_values(
    "date",
    ascending=False,
)

st.subheader("Filters")
filter_col1, filter_col2, filter_col3 = st.columns(3)

# Transaction type
with filter_col1:
    available_types = sorted(df["type"].dropna().astype(str).unique())
    selected_types = st.multiselect(
        "Transaction type",
        options=available_types,
        default=available_types,
    )

# Asset
with filter_col2:
    available_assets = sorted(df["name"].dropna().astype(str).unique())
    selected_assets = st.multiselect(
        "Asset",
        options=available_assets,
    )

# Date range
with filter_col3:
    min_date = df["date"].min().date()
    max_date = df["date"].max().date()

    selected_dates = st.date_input(
        "Date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    if not (isinstance(selected_dates, tuple) and len(selected_dates) == 2):
        st.caption("Select an end date to apply the date filter.")

filtered_df = df.copy()
if selected_types:
    filtered_df = filtered_df[filtered_df["type"].isin(selected_types)]
if selected_assets:
    filtered_df = filtered_df[filtered_df["name"].isin(selected_assets)]
if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
    start_date, end_date = selected_dates
    filtered_df = filtered_df[
        (filtered_df["date"].dt.date >= start_date) & (filtered_df["date"].dt.date <= end_date)
    ]

# ---------------------------------------------------------
# TRANSACTION METRICS
# ---------------------------------------------------------

total_transactions = len(filtered_df)
buys = filtered_df[filtered_df["type"] == "BUY"]
sells = filtered_df[filtered_df["type"] == "SELL"]
dividends = filtered_df[filtered_df["type"] == "DIVIDEND"]
fees = filtered_df["fee"].sum()
taxes = filtered_df["tax"].sum()

# Net transaction cash flow
net_cash_flow = filtered_df["amount"].sum() + filtered_df["fee"].sum() + filtered_df["tax"].sum()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric(
    "Transactions",
    f"{total_transactions:,}",
)
col2.metric(
    "Buys",
    f"{len(buys):,}",
)
col3.metric(
    "Sells",
    f"{len(sells):,}",
)
col4.metric(
    "Dividends",
    f"{len(dividends):,}",
)
col5.metric(
    "Net cash flow",
    f"€{net_cash_flow:,.2f}",
)

# ---------------------------------------------------------
# TRANSACTIONS OVER TIME
# ---------------------------------------------------------
TYPE_GROUPS = {
    "BUY": "Buy",
    "SELL": "Sell",
    "DIVIDEND": "Dividend",
    "INTEREST_PAYMENT": "Interest",
    "TRANSFER_INBOUND": "Deposit",
    "TRANSFER_INSTANT_INBOUND": "Deposit",
    "CUSTOMER_INPAYMENT": "Deposit",
    "TRANSFER_INSTANT_OUTBOUND": "Withdrawal",
    "CARD_TRANSACTION": "Card payment",
    "CUSTOMER_INPAYMENT_REVERSAL": "Other",
    "TAX_OPTIMIZATION": "Other",
}
GROUP_ORDER = [
    "Buy",
    "Sell",
    "Dividend",
    "Interest",
    "Deposit",
    "Withdrawal",
    "Card payment",
    "Other",
]
GROUP_COLORS = {g: CATEGORICAL[i % len(CATEGORICAL)] for i, g in enumerate(GROUP_ORDER)}

left_column, right_column = st.columns(2)
with left_column:
    with st.container(border=True):
        st.markdown("### Transactions over time")
        st.caption("Monthly transaction count by type.")

        hide_cards = st.toggle("Hide card payments", value=False)

        chart_df = filtered_df.assign(
            type_group=filtered_df["type"].map(TYPE_GROUPS).fillna("Other")
        )
        if hide_cards:
            chart_df = chart_df[chart_df["type_group"] != "Card payment"]
        transaction_chart = chart_df.groupby(["month", "type_group"], as_index=False).size()
        if transaction_chart.empty:
            st.info("No transactions for the selected filters.")
        else:
            figure = px.bar(
                transaction_chart,
                x="month",
                y="size",
                color="type_group",
                category_orders={"type_group": GROUP_ORDER},
                labels={
                    "month": "",
                    "size": "Transactions",
                    "type": "",
                },
            )
            figure.update_traces(hovertemplate="%{fullData.name}: %{y}<extra></extra>")
            figure.update_layout(
                hovermode="x unified",  # one tooltip per month listing all types
                bargap=0.15,
                legend=dict(orientation="h", yanchor="top", y=-0.12, x=0, title=None),
            )
            show_chart(figure)

# ---------------------------------------------------------
# CASH FLOW
# ---------------------------------------------------------
with right_column:
    with st.container(border=True):
        st.markdown("### Cash flow")
        st.caption("Net monthly cash movement after fees and taxes.")

        cash_flow = filtered_df.copy()
        cash_flow["net_cash_flow"] = cash_flow["amount"] + cash_flow["fee"] + cash_flow["tax"]
        monthly_cash_flow = cash_flow.groupby("month", as_index=False)["net_cash_flow"].sum()
        figure = px.bar(
            monthly_cash_flow,
            x="month",
            y="net_cash_flow",
            color="net_cash_flow",
            color_continuous_scale=DIVERGING,
            color_continuous_midpoint=0,
            labels={
                "month": "",
                "net_cash_flow": "Net cash flow (€)",
            },
        )
        figure.add_hline(
            y=0,
            line_width=1,
        )
        show_chart(figure)

# ---------------------------------------------------------
# TRANSACTION TYPE BREAKDOWN
# ---------------------------------------------------------
breakdown_col1, breakdown_col2 = st.columns(2)
with breakdown_col1:
    with st.container(border=True):
        st.markdown("### Transaction breakdown")
        st.caption("Share of each transaction type.")

        type_summary = filtered_df["type"].value_counts().reset_index()
        type_summary.columns = [
            "type",
            "count",
        ]
        figure = px.pie(
            type_summary,
            values="count",
            names="type",
            hole=0.68,
        )
        figure.update_traces(marker=dict(line=dict(color="#10151d", width=2)))
        figure.update_layout(
            legend=dict(orientation="h", yanchor="top", y=-0.12, x=0, title=None),
        )
        show_chart(figure)

with breakdown_col2:
    with st.container(border=True):
        st.markdown("### Transactions by asset class")
        st.caption("How many transactions each asset class accounts for.")

        if filtered_df["type"].isin(["BUY", "SELL"]).any():
            asset_summary = filtered_df.groupby("asset_class", as_index=False).size()
            asset_summary.columns = [
                "asset_class",
                "count",
            ]
            figure = px.bar(
                asset_summary,
                x="asset_class",
                y="count",
                labels={
                    "asset_class": "Asset class",
                    "count": "Transactions",
                },
            )
            figure.update_traces(marker_color=CATEGORICAL[0])
            show_chart(figure)
        else:
            st.info("No buy or sell transactions for the selected filters.")

# ---------------------------------------------------------
# FEES & TAXES
# ---------------------------------------------------------
st.markdown('<div class="section-label">FEES &amp; TAXES</div>', unsafe_allow_html=True)
fee_col1, fee_col2, fee_col3 = st.columns(3)
fee_col1.metric(
    "Fees",
    f"€{fees:,.2f}",
)
fee_col2.metric(
    "Taxes",
    f"€{taxes:,.2f}",
)
fee_col3.metric(
    "Fees + taxes",
    f"€{fees + taxes:,.2f}",
)

# ---------------------------------------------------------
# TRANSACTION TABLE
# ---------------------------------------------------------

st.subheader(f"Transaction History ({len(filtered_df):,})")
display_columns = [
    "date",
    "type",
    "name",
    "asset_class",
    "shares",
    "price",
    "amount",
    "fee",
    "tax",
]
available_columns = [column for column in display_columns if column in filtered_df.columns]
transaction_table = filtered_df[available_columns].copy()
st.dataframe(
    transaction_table,
    width="stretch",
    hide_index=True,
    column_config={
        "date": st.column_config.DateColumn(
            "Date",
            format="DD.MM.YYYY",
        ),
        "type": st.column_config.TextColumn(
            "Type",
        ),
        "name": st.column_config.TextColumn(
            "Asset",
        ),
        "asset_class": st.column_config.TextColumn(
            "Asset class",
        ),
        "shares": st.column_config.NumberColumn(
            "Shares",
            format="%.4f",
        ),
        "price": st.column_config.NumberColumn(
            "Price",
            format="€%.2f",
        ),
        "amount": st.column_config.NumberColumn(
            "Amount",
            format="€%.2f",
        ),
        "fee": st.column_config.NumberColumn(
            "Fee",
            format="€%.2f",
        ),
        "tax": st.column_config.NumberColumn(
            "Tax",
            format="€%.2f",
        ),
    },
)

with st.expander("View all Transactions data"):
    st.dataframe(df, width="stretch", hide_index=True)
