import pandas as pd
import plotly.express as px
import streamlit as st
from utils.chart import CATEGORICAL, NEGATIVE, show_chart
from utils.import_data import check_if_data_loaded, validate_data
from utils.styling import setup_page

setup_page("Dividends", "💸")

check_if_data_loaded()
df = st.session_state["df"]
validate_data(df)
dividends = df[df["type"] == "DIVIDEND"].copy()

if dividends.empty:
    st.info("No dividend payments were found in the currently loaded export.")
    st.stop()

period_options = (
    "All time",
    "Current year",
    "Last 12 months",
    "Custom range",
)
min_date = dividends["date"].min()
max_date = dividends["date"].max()
dividends["net_income"] = dividends["amount"] + dividends["tax"]

header_left, header_right = st.columns(
    [3.5, 1],
    vertical_alignment="bottom",
)

with header_right:
    st.caption("PERIOD")
    period = st.selectbox(
        "Period",
        period_options,
        label_visibility="collapsed",
    )
    if period == "Custom range":
        selected_dates = st.date_input(
            "Custom date range",
            value=(min_date.date(), max_date.date()),
            min_value=min_date.date(),
            max_value=max_date.date(),
        )
        if len(selected_dates) != 2:
            st.warning("Please select a start and an end date")
            st.stop()

if period == "Custom range":
    start_date, end_date = selected_dates
    filtered_dividends = dividends[
        (dividends["date"].dt.date >= start_date) & (dividends["date"].dt.date <= end_date)
    ].copy()
elif period == "Current year":
    filtered_dividends = dividends[dividends["date"].dt.year == pd.Timestamp.today().year].copy()
elif period == "Last 12 months":
    start_date = max_date - pd.DateOffset(months=12)
    filtered_dividends = dividends[dividends["date"] >= start_date].copy()
else:
    filtered_dividends = dividends.copy()

if filtered_dividends.empty:
    st.warning("No dividend payments were found for the selected period.")
    st.stop()

total_gross = filtered_dividends["amount"].sum()
total_tax = filtered_dividends["tax"].abs().sum()
total_net = filtered_dividends["net_income"].sum()
payments = len(filtered_dividends)
paying_assets = filtered_dividends["name"].nunique()
average_payment = total_net / payments if payments else 0
effective_tax_rate = total_tax / total_gross if total_gross else 0

monthly_income = (
    filtered_dividends.groupby("month", as_index=False)
    .agg(
        gross_dividends=("amount", "sum"),
        taxes_paid=("tax", lambda values: values.abs().sum()),
        net_dividends=("net_income", "sum"),
    )
    .sort_values("month")
)

best_month = monthly_income.loc[monthly_income["net_dividends"].idxmax()]

st.markdown(
    '<div class="section-label">DIVIDEND SUMMARY</div>',
    unsafe_allow_html=True,
)

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("Net dividends", f"€{total_net:,.2f}")
with col2:
    st.metric("Gross dividends", f"€{total_gross:,.2f}")
with col3:
    st.metric("Taxes paid", f"€{total_tax:,.2f}")
with col4:
    st.metric("Payments", payments)
with col5:
    st.metric("Paying assets", paying_assets)

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Average net payment", f"€{average_payment:,.2f}")
with col2:
    st.metric("Effective tax rate", f"{effective_tax_rate:.1%}")
with col3:
    st.metric(
        "Best month",
        str(best_month["month"]),
        delta=f"€{best_month['net_dividends']:,.2f} net",
    )

st.markdown(
    '<div class="section-label">INCOME OVER TIME</div>',
    unsafe_allow_html=True,
)

left_column, right_column = st.columns(2)
with left_column:
    with st.container(border=True):
        st.markdown("### Monthly net income")

        st.caption("Net dividend income received each month after taxes.")
        monthly_net_chart = px.bar(
            monthly_income,
            x="month",
            y="net_dividends",
            labels={"month": "Month", "net_dividends": "Net dividends (€)"},
            color_discrete_sequence=[CATEGORICAL[2]],
        )
        monthly_net_chart.update_layout(
            showlegend=False,
        )
        monthly_net_chart.update_yaxes(
            tickprefix="€",
            tickformat=",.0f",
        )

        show_chart(monthly_net_chart, height=400)

with right_column:
    with st.container(border=True):
        st.markdown("### Gross dividends vs taxes")
        st.caption("Compare gross dividend income with taxes paid each month.")

        monthly_gross_tax_chart = px.bar(
            monthly_income,
            x="month",
            y=["gross_dividends", "taxes_paid"],
            barmode="group",
            labels={
                "month": "Month",
                "value": "Amount (€)",
                "variable": "Metric",
            },
            color_discrete_map={
                "gross_dividends": CATEGORICAL[0],
                "taxes_paid": NEGATIVE,
            },
        )
        monthly_gross_tax_chart.for_each_trace(
            lambda trace: trace.update(
                name="Gross dividends" if trace.name == "gross_dividends" else "Taxes paid"
            )
        )
        show_chart(monthly_gross_tax_chart, height=400)

asset_summary = (
    filtered_dividends.groupby(["name", "symbol"], as_index=False)
    .agg(
        gross_dividends=("amount", "sum"),
        taxes_paid=("tax", lambda values: values.abs().sum()),
        net_dividends=("net_income", "sum"),
        payments=("amount", "count"),
        last_payment=("date", "max"),
    )
    .sort_values("net_dividends", ascending=False)
)
asset_summary["average_payment"] = asset_summary["net_dividends"] / asset_summary["payments"]

st.markdown(
    '<div class="section-label">INCOME SOURCES</div>',
    unsafe_allow_html=True,
)

left_column, right_column = st.columns([1.25, 1])

with left_column:
    with st.container(border=True):
        st.markdown("### Top dividend-paying assets")
        st.caption("Assets contributing the most net dividend income.")
        top_assets = asset_summary.head(5).sort_values("net_dividends")

        top_assets_chart = px.bar(
            top_assets,
            x="net_dividends",
            y="name",
            orientation="h",
            labels={"net_dividends": "Net dividends (€)", "name": "Asset"},
            color_discrete_sequence=[CATEGORICAL[2]],
        )
        top_assets_chart.update_xaxes(
            tickprefix="€",
            tickformat=",.0f",
        )
        show_chart(top_assets_chart, height=320)

with right_column:
    with st.container(border=True):
        st.markdown("### Income distribution")
        st.caption("Share of total net dividend income by asset.")

        # A donut stays readable to about six segments, so keep the five
        # largest payers and fold the rest into a single "Other" slice.
        distribution = asset_summary[["name", "net_dividends"]].copy()
        if len(distribution) > 6:
            tail = distribution.iloc[5:]["net_dividends"].sum()
            distribution = pd.concat(
                [
                    distribution.head(5),
                    pd.DataFrame([{"name": "Other", "net_dividends": tail}]),
                ],
                ignore_index=True,
            )

        distribution_chart = px.pie(
            distribution,
            names="name",
            values="net_dividends",
            hole=0.68,
        )
        distribution_chart.update_traces(
            textposition="inside",
            textinfo="percent",
            hovertemplate="<b>%{label}</b><br>Net dividends: €%{value:,.2f}<extra></extra>",
        )
        distribution_chart.update_layout(
            showlegend=False,
        )
        distribution_chart.add_annotation(
            text=(f"<b>€{total_net:,.2f}</b><br><span style='font-size:11px'>Net income</span>"),
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(
                size=15,
                color="#e6eaf0",
            ),
        )
        show_chart(distribution_chart, height=320)


st.markdown(
    """
    <div class="section-header">
        <h2>Dividend income by asset</h2>
        <p>
            Dividend income, taxes and payment activity
            for each income-producing asset.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)
display_summary = asset_summary[
    [
        "name",
        "gross_dividends",
        "taxes_paid",
        "net_dividends",
        "payments",
        "average_payment",
        "last_payment",
    ]
].copy()

st.dataframe(
    display_summary,
    width="stretch",
    hide_index=True,
    column_config={
        "name": "Asset",
        "gross_dividends": st.column_config.NumberColumn(
            "Gross dividends",
            format="€%.2f",
        ),
        "taxes_paid": st.column_config.NumberColumn(
            "Taxes paid",
            format="€%.2f",
        ),
        "net_dividends": st.column_config.NumberColumn(
            "Net dividends",
            format="€%.2f",
        ),
        "payments": st.column_config.NumberColumn("Payments", format="%d"),
        "average_payment": st.column_config.NumberColumn(
            "Average payment",
            format="€%.2f",
        ),
        "last_payment": st.column_config.DateColumn(
            "Last payment",
            format="DD MMM YYYY",
        ),
    },
)


with st.expander("View dividend transactions"):
    raw_dividends = filtered_dividends[
        ["date", "name", "symbol", "shares", "amount", "tax", "net_income", "currency"]
    ].sort_values("date", ascending=False)

    st.dataframe(
        raw_dividends,
        width="stretch",
        hide_index=True,
        column_config={
            "date": st.column_config.DateColumn("Date", format="DD MMM YYYY"),
            "name": "Asset",
            "symbol": "Symbol / ISIN",
            "shares": st.column_config.NumberColumn("Shares", format="%.4f"),
            "amount": st.column_config.NumberColumn("Gross dividend", format="€%.2f"),
            "tax": st.column_config.NumberColumn("Tax", format="€%.2f"),
            "net_income": st.column_config.NumberColumn("Net dividend", format="€%.2f"),
            "currency": "Currency",
        },
    )
