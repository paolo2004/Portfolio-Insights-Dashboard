import streamlit as st
from utils.data_source import ensure_data_loaded, render_data_source_card

# Overview is the default page: the app opens straight onto the numbers.
PAGES = [
    st.Page("pages/1_📊_Overview.py", title="Overview", icon=":material/dashboard:", default=True),
    st.Page(
        "pages/2_🥧_Allocation.py",
        title="Asset allocation",
        icon=":material/donut_small:",
        url_path="allocation",
    ),
    st.Page(
        "pages/3_💸_Dividends.py",
        title="Dividends",
        icon=":material/attach_money:",
        url_path="dividends",
    ),
    st.Page(
        "pages/4_🔁_Transactions.py",
        title="Transactions",
        icon=":material/swap_horiz:",
        url_path="transactions",
    ),
    st.Page(
        "pages/7_💰_Realised_Gains.py",
        title="Realised gains",
        icon=":material/trending_up:",
        url_path="realised-gains",
    ),
    st.Page(
        "pages/5_💳_Expenses.py",
        title="Expenses",
        icon=":material/credit_card:",
        url_path="expenses",
    ),
    st.Page(
        "pages/6_📈_Asset_Analysis.py",
        title="Asset analysis",
        icon=":material/search:",
        url_path="asset-analysis",
    ),
]

page = st.navigation(PAGES)
ensure_data_loaded()
render_data_source_card()
page.run()
