# Report: How Fragile Is a Fixed Withdrawal Rate?

## Verdict

A fixed real withdrawal of four percent of the starting balance survives almost
every historical thirty-year window in this dataset, but the margin comes from a
handful of extraordinary decades rather than from the strategy being robust. The
failures cluster entirely in windows that begin at a high valuation and meet poor
real returns in the first decade.

## The sweep

Across every start month in the series, a thirty-year horizon, and a sixty-forty
allocation rebalanced annually, the fixed four percent rule exhausts the portfolio
in a small minority of windows. Raising the rate by a single percentage point more
than doubles that failure count, which is the clearest result in the whole sweep.

## Sequence-of-returns risk dominates

The order of returns matters far more than their average. Two windows with nearly
identical thirty-year averages diverge completely when one front-loads its bad
years, because withdrawals during a drawdown sell more shares to raise the same
real income and the portfolio never recovers the share count.

## Where the result is weakest

The dataset is a single country over a period in which that country's equity market
was unusually strong. Treating this as the base rate for the future is the main
hazard, and nothing in the backtest can correct for it.

## What actually moves the outcome

Flexibility. Cutting withdrawals by ten percent for the two years following a
twenty percent drawdown removes most of the failures, and it does so without
forecasting anything — it only reacts to what already happened.
