# Security Policy

Portfolio Insights Dashboard works with personal financial data, so security and privacy problems
are taken seriously.

## Reporting a problem

Please **do not open a public issue** for a security problem. Report it privately through
GitHub's [private vulnerability reporting](https://github.com/paolo2004/portfolio-insights-dashboard/security/advisories/new)
instead.

Please include:

- what the problem is and where it is (file, page or function)
- how to reproduce it
- what could happen if someone used it

**Never attach a real transaction export.** Use the demo file `assets/demo_transactions.csv` or a
made-up file instead.

## Supported versions

Only the latest version on the `main` branch gets security fixes.

## What the app does to protect your data

- Imported files are held in memory for the browser session only. They are never written to disk
  or uploaded.
- Sensitive columns (`counterparty_iban`, `payment_reference`, `account_type`, `mcc_code`) are
  removed as soon as a file is imported.
- Only ISINs and ticker symbols are sent out, to OpenFIGI and Yahoo Finance, to look up market
  data. Amounts, share counts, dates, names and IBANs never leave the machine.
- No login details are asked for or stored, and there is no tracking.
- `.gitignore` excludes `data/`, all `.csv`, `.xls` and `.xlsx` files and `.env`, so exports
  can't be committed by accident. The only exception is the demo portfolio.
- Every push is scanned with [Bandit](https://bandit.readthedocs.io) in CI.

## If you committed your own data by mistake

Deleting the file in a new commit is **not enough**: it stays in the Git history. Remove it from the
history (for example with [`git filter-repo`](https://github.com/newren/git-filter-repo)), force-push,
and treat anything in the file, such as your IBAN, as exposed.
