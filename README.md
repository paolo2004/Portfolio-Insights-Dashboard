<div align="center">

# Portfolio Insights Dashboard

**See where your money is, what it earns and what it costs, all in one place.**

A free dashboard that runs on your own computer. Give it the transaction export from your
Trade Republic account, and it turns hundreds of rows into clear charts and plain numbers.

[![CI](https://github.com/paolo2004/portfolio-insights-dashboard/actions/workflows/ci.yml/badge.svg)](https://github.com/paolo2004/portfolio-insights-dashboard/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Streamlit](https://img.shields.io/badge/streamlit-1.58-red)

</div>

## Why

Your broker app shows what your account is worth today. Your export file holds much more: how much
you really put in, which sales made money, what you earned in dividends and paid in fees. It's just
hard to read. This dashboard does the maths for you, and it is:

- **Private**: your file never leaves your computer. No account, no login, no tracking.
- **Honest**: if a number can't be worked out properly, it tells you instead of guessing.
- **Simple**: every page answers one question. No finance knowledge needed.

## Get started

You need **Python 3.12**. Then run:

```powershell
git clone https://github.com/paolo2004/portfolio-insights-dashboard.git
cd portfolio-insights-dashboard
python -m venv venv
.\venv\Scripts\Activate.ps1        # macOS / Linux: source venv/bin/activate
pip install -r requirements.txt
streamlit run app/main.py
```

The dashboard opens at <http://localhost:8501> with a **demo portfolio**, so you can look around
right away.

**To use your own data**, export your transactions from the Trade Republic app as a CSV file, then
click **Import CSV** on the Overview page (or **Replace file** in the sidebar). Export your **full
history from the day you opened the account**, otherwise numbers like your cash balance will be off.

## Pages

| Page                 | Answers                                                                                                                                    |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| **Overview**         | _How am I doing?_ Portfolio value, cash, dividends, assets held and realised profit, plus a chart of money put in vs. what it's worth now. |
| **Asset allocation** | _Where is my money?_ Split by type, single stock, crypto, country and industry.                                                            |
| **Dividends**        | _What do my investments pay me?_ Income before and after tax, top payers, month by month.                                                  |
| **Transactions**     | _What did I do, and when?_ Full filterable history, money in and out, fees and taxes.                                                      |
| **Realised gains**   | _Did my sales make money?_ Every sale with buy and sell price, profit after tax and holding time.                                          |
| **Expenses**         | _Where does my card money go?_ Card spending over time and top shops.                                                                      |
| **Asset analysis**   | _What is this thing I own?_ Prices and key facts for any stock, fund or coin.                                                              |

## A few terms

| Term                 | Meaning                                                              |
| -------------------- | -------------------------------------------------------------------- |
| **Invested capital** | Money you spent on buying, minus money you got back from selling.    |
| **Cost basis**       | What you paid for the shares you still own, fees included.           |
| **Unrealised P/L**   | Profit or loss "on paper" on things you still own.                   |
| **Realised P/L**     | Profit or loss you locked in by selling.                             |
| **Dividend**         | A payment some companies and funds make to their shareholders.       |
| **Yield on cost**    | Last 12 months of dividends as a percentage of what you paid.        |
| **ISIN / ticker**    | A security's ID (`US0378331005`) and its short market name (`AAPL`). |

### How profit on a sale is worked out

The dashboard uses **FIFO (first in, first out)**: the shares you bought first count as sold first.
This is also how German tax rules work.

> You buy 10 shares at €100, later 10 more at €120, then sell 15 at €130 (€1,950).
> Those 15 shares are the 10 from the first buy and 5 from the second, so they cost you €1,600.
> **Profit: €350** before tax. You still own 5 shares that cost €600.

Fees are added to the cost when you buy and taken off what you receive when you sell.

## Privacy

- **Stays on your computer:** amounts, share counts, dates, your name and bank details. Imported
  files are kept in memory only, never saved or uploaded. Bank account numbers and payment
  references are removed on import.
- **Sent out:** only the IDs of the securities you hold (ISINs and tickers), to
  [OpenFIGI](https://www.openfigi.com/api) and [Yahoo Finance](https://finance.yahoo.com), to get
  prices. Without internet everything still works, just without live prices.
- **Never:** no Trade Republic login, no connection to Trade Republic, no tracking.

Your exports are git-ignored so they can't end up on GitHub. See [SECURITY.md](SECURITY.md) for
more, and for how to report a problem.

## Good to know

- Only euros and US dollars are converted. Other currencies are counted at what you paid.
- The import dialog accepts CSV only for now.
- Yahoo Finance is unofficial, so now and then a security shows no market data.
- This is not financial or tax advice. For your tax return, use your broker's official documents.

## For developers

```powershell
pip install -r requirements-dev.txt
pytest              # 216 tests, fully offline (network calls are mocked and blocked)
ruff check .        # lint
ruff format .       # format
bandit -r app       # security scan
```

CI runs all four on every push and pull request to `main`.

### Project structure

All calculations live in `app/utils/`, separate from the pages, so they can be tested without
Streamlit.

```text
portfolio-insights-dashboard/
├── app/
│   ├── main.py                  Entry point: sidebar navigation, demo data, data source card
│   ├── pages/                   One file per page
│   │   ├── 1_📊_Overview.py
│   │   ├── 2_🥧_Allocation.py
│   │   ├── 3_💸_Dividends.py
│   │   ├── 4_🔁_Transactions.py
│   │   ├── 5_💳_Expenses.py
│   │   ├── 6_📈_Asset_Analysis.py
│   │   └── 7_💰_Realised_Gains.py
│   ├── utils/
│   │   ├── data_source.py       Demo portfolio, import dialog, sidebar data source card
│   │   ├── import_data.py       Loads, cleans and validates the export
│   │   ├── ticker_lookup.py     Turns ISINs into tickers via OpenFIGI
│   │   ├── metrics.py           FIFO positions, realised trades, allocation, currency conversion
│   │   ├── overview.py          Invested capital, cash and value timelines
│   │   ├── analysis.py          Market data, number formatting, asset analysis views
│   │   ├── chart.py             Chart theme and colour palette
│   │   └── styling.py           Shared page setup: config, stylesheets, chart theme
│   └── styles/
│       ├── tokens.css           Design tokens: colours, radii, spacing
│       └── main.css             Component styling
├── assets/
│   ├── demo_transactions.csv    Demo portfolio loaded on start
│   └── logo.webp
├── data/                        Your own exports (git-ignored)
├── tests/                       216 offline tests
├── .github/workflows/ci.yml     Lint, format, test and security checks
├── .streamlit/config.toml       Dark theme matching the design tokens
├── pyproject.toml               Ruff and pytest settings
├── requirements.txt             App dependencies
├── requirements-dev.txt         Plus test and lint tools
├── REQUIREMENTS.md              Project requirements (German)
└── SECURITY.md                  Security policy
```

**Adding a page.** Create a file in `app/pages/` that starts with
`setup_page("Title", ":material/icon:")` from `utils.styling`, then add it to the `PAGES` list in
`app/main.py`.

**Import format.** The required columns are `date`, `type`, `name`, `shares`, `amount` and
`currency`. See `assets/demo_transactions.csv` for the full layout.

**Built with** Python 3.12, Streamlit, pandas, NumPy, Plotly, yfinance, pytest, Ruff and Bandit.
Requirements are documented in German in [REQUIREMENTS.md](REQUIREMENTS.md).

---

<div align="center">
<sub>An independent project, not affiliated with or endorsed by Trade Republic.</sub>
</div>
