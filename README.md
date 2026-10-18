# Portfolio-Insights-Dashboard

A local Streamlit dashboard that imports, analyses and visualises your Trade Republic export file. Your transaction data stays on your own machine.

![Python](https://img.shields.io/badge/python-3.12-blue)
![Streamlit](https://img.shields.io/badge/streamlit-1.58-red)

## Quick start

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app/main.py
```

The dashboard opens at <http://localhost:8501>, straight onto the **Overview** page. It loads a demo portfolio automatically, so you can explore every page before importing anything of your own.

To use your own data, export your transactions from the Trade Republic app as CSV, then click **Import CSV** on the Overview page or **Replace file** in the sidebar's *Data source* card. The same dialog lets you switch back to the demo portfolio.

## Features

Navigation is a sidebar built with `st.navigation`. The *Data source* card at the top of the sidebar always shows which file is loaded and how many rows it has.

| Page | What it shows |
| --- | --- |
| **Overview** | KPI cards (portfolio value with unrealised P/L, cash, dividends with 12-month yield on cost, assets held, transactions per month), an invested capital vs market value chart, an allocation donut by asset class including cash, and recent activity. A 1M / 6M / 1Y / All selector sets the period. |
| **Asset allocation** | Invested capital by asset class, equity position, crypto position, country and sector, plus net capital invested per trading day |
| **Dividends** | Net and gross dividend income, taxes paid, effective tax rate, top-paying assets and income distribution |
| **Transactions** | Filterable transaction history with monthly activity, cash flow, type and asset class breakdowns, and fee/tax totals |
| **Expenses** | Card spending over time, top merchants, and fee/tax totals |
| **Asset analysis** | Market data and fundamentals for any holding, with separate views for stocks, funds/ETFs and crypto |

### How the numbers are calculated

Positions use **average-cost accounting**. A buy adds shares and cost (trade amount plus fees and taxes). A sell reduces the open share count and removes a proportional share of the cost basis, and the difference between net proceeds and removed cost basis is booked as realised P/L. A sale larger than the holding only removes the shares on hand.

The Overview builds on those positions:

- **Invested capital** is the net cash put into trades: buys count with their fees and taxes, and sales count with what came back after fees and taxes. Every page uses this one definition (`net_invested` in `utils/overview.py`).
- **Cash** is the sum of every cash movement in the export (`amount + fee + tax`). This only works when the export starts at account opening. A negative result is flagged as a probably partial export.
- **Portfolio value** is the market value of the open positions plus any positive cash. Each position is valued at its latest close in EUR. If there is no price, it falls back to its cost basis, and the KPI card says how many positions were valued at cost.
- **Unrealised P/L** is that market value minus the remaining cost basis.
- **The market value line** on the invested capital chart appears only when every held asset has price history. A partial line would sit below the invested line and look like a loss.

Sign conventions follow the Trade Republic export: `amount` is negative for buys and positive for sells, and `fee` and `tax` are negative.

## Data sources

**Local files: your transaction data.** The CSV export from Trade Republic. An imported file is held in the Streamlit session, in memory only. It is never written to disk or sent anywhere. The loader can also read Excel files (`.xls`/`.xlsx`), but the import dialog currently accepts only CSV.

**External APIs — market data only.** The dashboard enriches your holdings with public market data:

| Service | What is sent | What comes back |
| --- | --- | --- |
| [OpenFIGI](https://www.openfigi.com/api) | The ISIN of each security you hold | The matching ticker symbol |
| [Yahoo Finance](https://finance.yahoo.com) (via `yfinance`) | Ticker symbols | Prices, company data, sectors, countries, financial statements, USD/EUR rate |

**This means your ISINs and ticker symbols leave your machine.** Amounts, share counts, dates, names and IBANs never do. Every lookup fails soft, so the app still works without network access: pages render, imported figures are correct, and anything price-derived is reported as unavailable.

Not supported, by design:

- No Trade Republic login automation and no credential storage
- No official or unofficial Trade Republic API access
- No automatic portfolio synchronisation
- No analytics, tracking or telemetry

## Privacy and security

| Question | Answer |
| --- | --- |
| What data is sensitive? | Securities, transactions, IBAN, name and other personal financial data |
| Where is it stored? | In memory for the current browser session; optionally your own copies in the git-ignored `data/` folder |
| What leaves the machine? | ISINs and ticker symbols, sent to OpenFIGI and Yahoo Finance for market data |
| Who has access? | Only the local user |
| What must never happen? | Financial data or credentials ending up on GitHub |

The importer drops the most sensitive columns (`counterparty_iban`, `payment_reference`, `account_type`, `mcc_code`) on load, so they never reach a chart or a table. `.gitignore` excludes `data/`, all `*.csv` and `*.xlsx` files, and `.env`, with an explicit exception for the demo portfolio.

## Architecture

```text
Trade Republic CSV  (or the bundled demo portfolio)
          |
          v
   Import dialog / demo loader  app/utils/data_source.py
          |
          v
   Import & validation          app/utils/import_data.py
          |
          +---> ISIN -> ticker  app/utils/ticker_lookup.py  --> OpenFIGI
          |
          v
   pandas DataFrame (st.session_state)
          |
          +---> positions, allocation      app/utils/metrics.py   --> Yahoo Finance
          +---> overview timelines, cash   app/utils/overview.py  --> Yahoo Finance
          +---> market data, formatting    app/utils/analysis.py  --> Yahoo Finance
          |
          v
   Navigation (st.navigation)    app/main.py
          |
          v
   Streamlit pages               app/pages/
          |
          v
   Shared styling & charts       app/utils/styling.py, app/utils/chart.py
```

Data processing lives in `app/utils/` and is kept separate from the pages, so analysis functions can be tested without a running Streamlit server.

## Project structure

```text
app/
  main.py              Entry point: sidebar navigation, demo data, data source card
  pages/               One file per dashboard page, registered in main.py
  utils/
    data_source.py     Demo portfolio loading, import dialog, sidebar source card
    import_data.py     File loading, normalisation and validation
    ticker_lookup.py   ISIN -> Yahoo Finance ticker resolution
    metrics.py         Position accounting, allocation, currency conversion
    overview.py        Overview calculations: invested capital, cash, holdings and
                       market value timelines, allocation by asset class
    analysis.py        Market data, formatting, asset analysis page
    chart.py           Plotly theme and validated colour palette
    styling.py         Page setup: config, stylesheets, chart theme
  styles/
    tokens.css         Design tokens: colours, radii, spacing
    main.css           Component styling
.streamlit/config.toml Dark theme matching the design tokens
assets/                Logo and the demo portfolio
data/                  Your own exports (git-ignored)
tests/                 Test suite
```

### Styling

Every page starts with a single call:

```python
from utils.styling import setup_page

setup_page("Overview", ":material/dashboard:")
```

Pages are registered in `app/main.py` with a title, a Material icon and a URL path. A new page needs an entry in the `PAGES` list there as well as a file in `app/pages/`.

That sets the page config, injects the stylesheets and registers the Plotly theme, so pages stay visually consistent without repeating boilerplate. Colours are defined once as CSS custom properties in `styles/tokens.css` and as Python constants in `utils/chart.py`.

The categorical chart palette is checked for colourblind separation against the dashboard's own surface colour. Because every slice of a pie chart is compared against every other, only the first three slots are safe in that form — which is why most breakdowns are sorted bar charts rather than pies.

## Testing

```powershell
pytest
```

188 tests covering file import and validation, ISIN lookup, the average-cost position accounting, allocation breakdowns, the Overview calculations (invested capital, cash balance, holdings and market value timelines, period windows), and the display formatters.

The suite runs **fully offline**: every OpenFIGI and Yahoo Finance call is mocked, and `tests/conftest.py` blocks socket creation so a test that forgets to mock one fails loudly instead of quietly hitting the network.

Two fixtures are worth knowing about if you add tests:

- `st.stop()` is patched to raise. Outside a Streamlit runtime it only logs a warning and returns, so guarded functions would otherwise keep running past the guard.
- Streamlit's caches are cleared between tests, so mocked lookups are not served stale results.

## Development

```powershell
pip install -r requirements-dev.txt

pytest              # tests
ruff check .        # lint
ruff format .       # format
bandit -r app       # security scan
```

`pyproject.toml` puts both the repository root and `app/` on the Python path, because the app modules import each other as `utils.<module>`.

## Tech stack

- **Python 3.12**
- **Streamlit** — dashboard UI
- **pandas** / **NumPy** — data processing
- **Plotly** — charts
- **yfinance** / **requests** — market data
- **openpyxl** — Excel import
- **pytest**, **ruff**, **bandit** — tests, linting, security scanning

## CI

`.github/workflows/ci.yml` runs on pushes and pull requests to `main` or `master`, and on manual dispatch. It installs dependencies, checks formatting and linting with Ruff, runs Pytest, and scans `app/` with Bandit.

No deployment stage is configured: the dashboard is designed to run locally, which keeps financial data off third-party servers. A CD stage could be added later for Docker or a self-hosted deployment.

## Known limitations

- The cash balance is only correct for an export that starts at account opening. A partial export gives a wrong, possibly negative, figure.
- Currency conversion only handles USD and EUR. Holdings in other currencies show no price: they are valued at cost, and the market value line is hidden.
- The import dialog accepts only CSV, even though the loader can read Excel.
- Yahoo Finance is an unofficial data source; tickers that cannot be resolved from an ISIN simply show no market data.
- ISIN lookups use a 15-second timeout each, so the first import without a working network connection is slow before it gives up.

## Requirements

Functional and non-functional requirements are documented in German in [REQUIREMENTS.md](REQUIREMENTS.md).
