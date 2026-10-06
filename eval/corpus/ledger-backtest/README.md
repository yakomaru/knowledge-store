# ledger-backtest

A small backtesting harness for fixed-withdrawal strategies over long historical
return series.

## What's inside

A cleaner for the raw monthly series, a withdrawal-rate sweep, and a deployment
schedule comparison. All output is CSV; there is no UI and there will not be one.

## Quick start

```bash
# 1. build the clean monthly real-return series
python -m ledger.clean --out data/monthly_real.csv

# 2. sweep withdrawal rates across every start month
python -m ledger.sweep --series data/monthly_real.csv --out out/sweep.csv

# 3. compare lump-sum against staged deployment
python -m ledger.deploy --series data/monthly_real.csv
```

## Method notes

Returns are real, not nominal — every series is deflated by the same CPI index
before anything else happens. Mixing a nominal return with a real withdrawal is
the single easiest way to produce a cheerful and wrong answer.

Rolling windows overlap, so the success rates across start months are not
independent observations. Treat the spread as a description of history rather than
as a confidence interval.

## Data source

Monthly index levels, dividends, earnings, and CPI from a public long-run dataset,
checked into `data/` so results are reproducible without a network fetch.
