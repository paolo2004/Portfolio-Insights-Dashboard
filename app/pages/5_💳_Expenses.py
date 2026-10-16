import plotly.express as px
import streamlit as st
from utils.chart import CATEGORICAL, show_chart
from utils.import_data import check_if_data_loaded, validate_data
from utils.styling import setup_page

setup_page("Expenses", "💳")

check_if_data_loaded()
df = st.session_state["df"].copy()
validate_data(df)

expenses = df[df["type"] == "CARD_TRANSACTION"].copy()
# Flip the sign so spending is positive; refunds stay negative and reduce the totals.
expenses["amount"] = -expenses["amount"]

if expenses.empty:
    st.info("No expense transactions found in the uploaded data.")
    st.stop()

st.markdown('<div class="section-label">EXPENSE SUMMARY</div>', unsafe_allow_html=True)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total expenses", f"€{expenses['amount'].sum():,.2f}")
col2.metric("Number of expenses", f"{len(expenses):,}")
col3.metric("Total fees", f"€{expenses['fee'].sum():,.2f}")
col4.metric("Total taxes", f"€{expenses['tax'].sum():,.2f}")

col1, col2 = st.columns([0.6, 0.4])

with col1:
    with st.container(border=True):
        st.markdown("### Expenses over time")
        st.caption("Total card spending per month.")

        expenses_over_time = expenses.groupby("month", as_index=False)["amount"].sum()
        figure = px.line(
            expenses_over_time,
            x="month",
            y="amount",
            labels={"month": "", "amount": "Expenses (€)"},
        )
        figure.update_traces(line_width=2)
        show_chart(figure, height=400)

with col2:
    with st.container(border=True):
        st.markdown("### Top merchants")
        st.caption("The ten merchants you spent the most with.")

        # A sorted bar, not a pie: with this many categories no colour palette
        # keeps every slice distinguishable, and the values are close enough
        # that comparing wedge angles is guesswork.
        expenses_by_category = (
            expenses.groupby("name", as_index=False)
            .agg(total_expenses=("amount", "sum"))
            .sort_values(by="total_expenses", ascending=True)
            .tail(10)
        )
        figure = px.bar(
            expenses_by_category,
            x="total_expenses",
            y="name",
            orientation="h",
            labels={"name": "", "total_expenses": "Spent (€)"},
        )
        figure.update_traces(marker_color=CATEGORICAL[0])
        show_chart(figure, height=400)

with st.expander("View detailed expenses data"):
    columns_to_display = [
        "date",
        "name",
        "amount",
        "currency",
    ]
    st.dataframe(
        expenses[columns_to_display],
        width="stretch",
        hide_index=True,
        column_config={
            "date": st.column_config.DateColumn("Date", format="DD.MM.YYYY"),
            "name": st.column_config.TextColumn("Merchant"),
            "amount": st.column_config.NumberColumn("Amount", format="€%.2f"),
            "currency": st.column_config.TextColumn("Currency"),
        },
    )
