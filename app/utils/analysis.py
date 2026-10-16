import pandas as pd
import plotly.express as px
import streamlit as st
import yfinance as yf
from utils.chart import show_chart
from utils.ticker_lookup import _validate_yahoo_ticker

PERIODS = {
    "1 Month": "1mo",
    "3 Months": "3mo",
    "6 Months": "6mo",
    "1 Year": "1y",
    "2 Years": "2y",
    "Year to Date": "ytd",
    "Maximum": "max",
}


def format_number(value, decimals=2):
    """Format numbers safely."""
    if value is None or pd.isna(value):
        return "N/A"
    try:
        return f"{float(value):,.{decimals}f}"
    except (ValueError, TypeError):
        return "N/A"


def format_large_number(value):
    """Format large numbers like market cap."""
    if value is None or pd.isna(value):
        return "N/A"
    try:
        value = float(value)
    except (ValueError, TypeError):
        return "N/A"

    if value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.2f} T"
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f} B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f} M"
    return f"{value:,.0f}"


def format_percentage(value, is_decimal=True):
    """Format a percentage.

    Yahoo Finance mixes units: most ratios are fractions (0.25 = 25%), but some
    fields such as `dividendYield` are already percentages (0.41 = 0.41%). The
    caller states which one it passes, because the value alone cannot tell.
    """
    if value is None or pd.isna(value):
        return "N/A"
    try:
        value = float(value)
    except (ValueError, TypeError):
        return "N/A"
    return f"{value * 100 if is_decimal else value:.2f}%"


def get_portfolio_data():
    """Return portfolio data from Streamlit session state."""
    portfolio_data = st.session_state.get("df")
    if portfolio_data is None or portfolio_data.empty:
        st.warning("No portfolio data found. Please upload your Trade Republic file first.")
        st.stop()
    return portfolio_data


def get_available_assets(portfolio_data):
    assets = (
        portfolio_data[["name", "symbol", "ticker", "asset_class"]]
        .dropna(subset=["name", "ticker"])
        .drop_duplicates()
        .sort_values("name")
        .reset_index(drop=True)
    )
    if assets.empty:
        st.warning("No assets with valid ticker symbols were found.")
        st.stop()
    return assets


def select_asset(assets):
    st.sidebar.header("Asset Lookup")
    selected_asset = st.sidebar.selectbox(
        "Select an asset from your portfolio", options=assets["name"].tolist()
    )
    manual_ticker_input = st.sidebar.text_input(
        "Or enter another Yahoo Finance ticker symbol",
        placeholder="Example: AAPL, MSFT, TSLA",
    )

    selected_row = assets.loc[assets["name"] == selected_asset].iloc[0]
    portfolio_ticker = str(selected_row["ticker"]).strip().upper()
    asset_class = str(selected_row["asset_class"]).strip().upper()

    if manual_ticker_input.strip():
        manual_ticker = manual_ticker_input.strip().upper()
        if not _is_valid_ticker(manual_ticker):
            st.sidebar.warning("Invalid ticker symbol.")
            return None, manual_ticker, None
        # The portfolio row's class does not apply to a typed ticker; the page
        # derives it from Yahoo Finance's quote type instead.
        return manual_ticker, manual_ticker, None
    return portfolio_ticker, selected_asset, asset_class


# Cached so typing a ticker does not re-query Yahoo Finance on every rerun.
_is_valid_ticker = st.cache_data(ttl=900, show_spinner=False)(_validate_yahoo_ticker)

QUOTE_TYPE_CLASSES = {
    "CRYPTOCURRENCY": "CRYPTO",
    "ETF": "FUND",
    "MUTUALFUND": "FUND",
}


def asset_class_from_info(info):
    """Asset class for a ticker that is not in the portfolio."""
    return QUOTE_TYPE_CLASSES.get(str(info.get("quoteType", "")).upper(), "STOCK")


def select_period():
    """Render the period selector and return the Yahoo Finance period."""
    selected_period = st.sidebar.selectbox("Select period", options=list(PERIODS), index=3)
    return PERIODS[selected_period]


# The fetchers below raise on failure: st.cache_data does not cache exceptions,
# so a temporary Yahoo Finance outage is retried instead of cached for 15 minutes.
@st.cache_data(ttl=900, show_spinner=False)
def _fetch_ticker_info(ticker_symbol):
    info = yf.Ticker(ticker_symbol).info
    return info if isinstance(info, dict) else {}


def load_ticker_info(ticker_symbol):
    """Load asset information from Yahoo Finance."""
    try:
        return _fetch_ticker_info(ticker_symbol)
    except Exception:
        return {}


@st.cache_data(ttl=900, show_spinner=False)
def _fetch_price_history(ticker_symbol, period):
    history = yf.Ticker(ticker_symbol).history(period=period, auto_adjust=False)
    if history.empty:
        return pd.DataFrame()
    history = history.reset_index()
    if "Date" not in history.columns and "Datetime" in history.columns:
        history = history.rename(columns={"Datetime": "Date"})
    return history


def load_price_history(ticker_symbol, period):
    """Load and normalize historical price data."""
    try:
        return _fetch_price_history(ticker_symbol, period)
    except Exception:
        return pd.DataFrame()


def get_display_name(info, asset_class, fallback=None):
    """Return the best available display name, or `fallback` when Yahoo has none."""
    if asset_class == "CRYPTO":
        name = info.get("name")
    else:
        name = info.get("longName")
    return name or info.get("shortName") or fallback


def get_asset_type(ticker_symbol, asset_class):
    """Return a display category for the selected asset."""
    return "Crypto" if asset_class == "CRYPTO" or ticker_symbol.endswith("-USD") else "Stock"


def calculate_price_metrics(history, one_year_history, info):
    """Calculate current price, change, 52-week range, and volume."""
    close_prices = history.get("Close", pd.Series(dtype=float)).dropna()
    latest_price = close_prices.iloc[-1] if not close_prices.empty else None
    if latest_price is None or pd.isna(latest_price):
        latest_price = info.get("currentPrice") or info.get("regularMarketPrice")

    previous_close = close_prices.iloc[-2] if len(close_prices) > 1 else latest_price
    price_change = None
    price_change_percent = None
    if latest_price is not None and previous_close is not None:
        price_change = latest_price - previous_close
        price_change_percent = price_change / previous_close * 100 if previous_close != 0 else 0

    metric_history = one_year_history if not one_year_history.empty else history
    metric_close = metric_history.get("Close", pd.Series(dtype=float)).dropna()
    volume_series = history.get("Volume", pd.Series(dtype=float)).dropna()
    return {
        "latest_price": latest_price,
        "price_change": price_change,
        "price_change_percent": price_change_percent,
        "high_52_week": metric_close.max() if not metric_close.empty else None,
        "low_52_week": metric_close.min() if not metric_close.empty else None,
        "volume": volume_series.iloc[-1] if not volume_series.empty else None,
    }


def format_price(value, currency):
    """Format a price with a currency symbol."""
    formatted_value = format_number(value, 2)
    if formatted_value == "N/A":
        return formatted_value
    symbols = {"USD": "$", "EUR": "€", "GBP": "£", "CHF": "CHF "}
    return f"{symbols.get(currency, currency + ' ')}{formatted_value}"


def render_price_metrics(metrics, currency):
    """Render the main price metric cards."""
    columns = st.columns(4)
    with columns[0]:
        st.metric(
            "Current Price",
            format_price(metrics["latest_price"], currency),
            f"{metrics['price_change_percent']:.2f}%"
            if metrics["price_change_percent"] is not None
            else None,
        )
    with columns[1]:
        st.metric("52-Week High", format_price(metrics["high_52_week"], currency))
    with columns[2]:
        st.metric("52-Week Low", format_price(metrics["low_52_week"], currency))
    with columns[3]:
        st.metric("Latest Volume", format_large_number(metrics["volume"]))


def render_price_chart(history, display_name, currency):
    """Render the historical closing-price chart."""
    st.subheader(f"Price History: {display_name}")
    chart_data = history.copy()
    chart_data["Date"] = pd.to_datetime(chart_data["Date"]).dt.tz_localize(None)
    figure = px.line(
        chart_data,
        x="Date",
        y="Close",
        labels={"Date": "Date", "Close": f"Price ({currency})"},
    )
    figure.update_layout(hovermode="x unified")
    show_chart(figure, height=500)


def render_metric_group(title, metrics):
    """Render a reusable group of Streamlit metrics."""
    st.subheader(title)
    columns = st.columns(len(metrics))
    for column, (label, value) in zip(columns, metrics.items(), strict=False):
        with column:
            st.metric(label, value)


def render_asset_overview(info, ticker_symbol, fallback_name):
    """Render general stock information."""
    st.subheader("Company Overview")
    first_column, second_column = st.columns(2)
    with first_column:
        st.write(f"**Company:** {get_display_name(info, 'STOCK', fallback_name)}")
        st.write(f"**Ticker:** {ticker_symbol}")
        st.write(f"**Sector:** {info.get('sector', 'N/A')}")
        st.write(f"**Industry:** {info.get('industry', 'N/A')}")
    with second_column:
        st.write(f"**Country:** {info.get('country', 'N/A')}")
        st.write(f"**Exchange:** {info.get('exchange', 'N/A')}")
        st.write(f"**Currency:** {info.get('currency', 'N/A')}")
        if info.get("website"):
            st.write(f"**Website:** [Visit website]({info['website']})")


def format_date_value(timestamp):
    """Convert a Yahoo Finance timestamp to a readable date."""
    if not timestamp:
        return "N/A"
    try:
        return pd.to_datetime(timestamp, unit="s").strftime("%Y-%m-%d")
    except (TypeError, ValueError, OverflowError):
        return "N/A"


def render_financial_statements(ticker_symbol):
    """Render the selected financial statement."""
    st.subheader("Financial Statements")
    statement_type = st.selectbox(
        "Select statement", ["Income Statement", "Balance Sheet", "Cash Flow"]
    )
    try:
        ticker = yf.Ticker(ticker_symbol)
        statement = {
            "Income Statement": ticker.income_stmt,
            "Balance Sheet": ticker.balance_sheet,
            "Cash Flow": ticker.cashflow,
        }[statement_type]
    except Exception:
        statement = pd.DataFrame()

    if statement is None or statement.empty:
        st.info("Financial statement data is not available.")
        return
    st.dataframe(statement, width="stretch")


def render_crypto_information(info, currency):
    """Render cryptocurrency-specific information."""

    max_supply = info.get("maxSupply")

    # Some cryptocurrencies have no defined maximum supply.
    # Yahoo Finance may return 0 in this case.
    if max_supply is None or max_supply == 0:
        max_supply = None
    total_supply = info.get("totalSupply")
    circulating_supply = info.get("circulatingSupply")

    st.subheader("Supply & Market Data")
    left_column, right_column = st.columns(2)
    with left_column:
        st.metric("Market Capitalization", format_large_number(info.get("marketCap")))
        st.metric("Fully Diluted Value", format_large_number(info.get("fullyDilutedValue")))
        st.metric("24h Trading Volume", format_large_number(info.get("volume24Hr")))

    with right_column:
        st.metric("Circulating Supply", format_large_number(circulating_supply))

        st.metric("Total Supply", format_large_number(total_supply))

        st.metric("Maximum Supply", format_large_number(max_supply))

    render_metric_group(
        "Historical Price Levels",
        {
            "All-Time High": format_price(info.get("allTimeHigh"), currency),
            "All-Time Low": format_price(info.get("allTimeLow"), currency),
            "50-Day Average": format_price(info.get("fiftyDayAverage"), currency),
            "200-Day Average": format_price(info.get("twoHundredDayAverage"), currency),
        },
    )

    render_metric_group(
        "Market Performance",
        {
            "52-Week Change": format_percentage(
                info.get("fiftyTwoWeekChangePercent"), is_decimal=False
            ),
            "From 52-Week High": format_percentage(info.get("fiftyTwoWeekHighChangePercent")),
            "From 52-Week Low": format_percentage(info.get("fiftyTwoWeekLowChangePercent")),
            "Volume / Market Cap": format_percentage(
                info.get("volume24HrMarketCapPercent"), is_decimal=False
            ),
        },
    )

    # --------------------------------------------------
    # Important Links
    # --------------------------------------------------

    st.subheader("Important Links")

    website = info.get("website")
    whitepaper = info.get("whitepaper")
    coinmarketcap = info.get("coinMarketCapLink")

    columns = st.columns(3)

    with columns[0]:
        if website:
            st.link_button("🌐 Website", website)

    with columns[1]:
        if whitepaper:
            st.link_button("📄 Whitepaper", whitepaper)

    with columns[2]:
        if coinmarketcap:
            st.link_button("📊 CoinMarketCap", coinmarketcap)


def render_fund_information(info, currency):
    """Render fund/ETF-specific information."""
    fund_inception_date = format_date_value(info.get("fundInceptionDate"))

    st.subheader("Fund Overview")
    left_column, right_column = st.columns(2)
    with left_column:
        st.metric("Fund Type", info.get("legalType", "N/A"))

        st.metric("Fund Family", info.get("fundFamily", "N/A"))

        st.metric("Inception Date", fund_inception_date)
    with right_column:
        st.metric("Exchange", info.get("fullExchangeName", "N/A"))

        st.metric("Currency", info.get("currency", currency))

        st.metric("Ticker", info.get("symbol", "N/A"))

    st.subheader("Fund Costs & Valuation")
    left_column, right_column = st.columns(2)
    with left_column:
        st.metric(
            "Net Expense Ratio",
            format_percentage(info.get("netExpenseRatio"), is_decimal=False),
        )
        st.metric("P/E Ratio", format_number(info.get("trailingPE")))
    with right_column:
        st.metric("50-Day Average", format_price(info.get("fiftyDayAverage"), currency))
        st.metric("200-Day Average", format_price(info.get("twoHundredDayAverage"), currency))

    st.subheader("Fund Performance")
    left_column, right_column = st.columns(2)
    with left_column:
        st.metric(
            "52-Week Performance",
            format_percentage(info.get("fiftyTwoWeekChangePercent"), is_decimal=False),
        )
        st.metric("From 52-Week High", format_percentage(info.get("fiftyTwoWeekHighChangePercent")))
    with right_column:
        st.metric("From 52-Week Low", format_percentage(info.get("fiftyTwoWeekLowChangePercent")))
        st.metric("All-Time High", format_price(info.get("allTimeHigh"), currency))

    st.subheader("Trading Information")
    left_column, right_column = st.columns(2)
    with left_column:
        st.metric("Latest Volume", format_large_number(info.get("regularMarketVolume")))
        st.metric("Average Volume", format_large_number(info.get("averageVolume")))
    with right_column:
        st.metric("Bid", format_price(info.get("bid"), currency))
        st.metric("Ask", format_price(info.get("ask"), currency))


def render_stock_information(info, ticker_symbol, fallback_name):
    """Render stock-specific information."""
    render_asset_overview(info, ticker_symbol, fallback_name)
    st.markdown("---")
    render_metric_group(
        "Valuation",
        {
            "Market Cap": format_large_number(info.get("marketCap")),
            "P/E Ratio": format_number(info.get("trailingPE")),
            "Dividend Yield": format_percentage(info.get("dividendYield"), is_decimal=False),
            "Price/Book": format_number(info.get("priceToBook")),
        },
    )
    render_metric_group(
        "Profitability",
        {
            "ROE": format_percentage(info.get("returnOnEquity")),
            "ROA": format_percentage(info.get("returnOnAssets")),
            "Profit Margin": format_percentage(info.get("profitMargins")),
            "Operating Margin": format_percentage(info.get("operatingMargins")),
        },
    )
    render_metric_group(
        "Growth",
        {
            "Revenue Growth": format_percentage(info.get("revenueGrowth")),
            "Earnings Growth": format_percentage(info.get("earningsGrowth")),
            "EPS": format_number(info.get("trailingEps")),
            "Forward EPS": format_number(info.get("forwardEps")),
        },
    )
    render_metric_group(
        "Dividends",
        {
            "Dividend Yield": format_percentage(info.get("dividendYield"), is_decimal=False),
            "Annual Dividend": format_number(info.get("dividendRate")),
            "Payout Ratio": format_percentage(info.get("payoutRatio")),
            "Ex-Dividend Date": format_date_value(info.get("exDividendDate")),
        },
    )
    if info.get("longBusinessSummary"):
        st.markdown("---")
        st.subheader("About the Company")
        st.write(info["longBusinessSummary"])
    st.markdown("---")
    render_financial_statements(ticker_symbol)


def render_asset_analysis_page():
    """Build the complete asset analysis page."""
    portfolio_data = get_portfolio_data()
    assets = get_available_assets(portfolio_data)

    ticker_symbol, fallback_name, asset_class = select_asset(assets)
    period = select_period()
    if not ticker_symbol:
        st.info("Select an asset or enter a valid ticker symbol to continue.")
        st.stop()

    with st.spinner("Loading market information..."):
        info = load_ticker_info(ticker_symbol)
        history = load_price_history(ticker_symbol, period)
        one_year_history = load_price_history(ticker_symbol, "1y")
    if history.empty:
        st.error(f"No market data found for ticker `{ticker_symbol}`.")
        st.stop()

    if asset_class is None:
        asset_class = asset_class_from_info(info)
    display_name = get_display_name(info, asset_class, fallback_name)
    currency = str(info.get("currency", "USD")).upper()
    metrics = calculate_price_metrics(history, one_year_history, info)
    st.header(display_name)
    render_price_metrics(metrics, currency)
    st.markdown("---")
    render_price_chart(history, display_name, currency)
    st.markdown("---")

    if get_asset_type(ticker_symbol, asset_class) == "Crypto":
        render_crypto_information(info, currency)
    elif asset_class == "FUND" or info.get("quoteType") == "ETF":
        render_fund_information(info, currency)
    else:
        render_stock_information(info, ticker_symbol, fallback_name)
