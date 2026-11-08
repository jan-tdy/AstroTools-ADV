## What it does

Confidence intervals for a binomial proportion k/n by four methods (`binom_conf_interval`).

## How to use

1. **k (successes)** and **n (trials)**: comma or space separated lists of the same length, or a single n for all.
2. **Confidence level** (default 0.68269, one sigma). **Interval**: `all`, `wilson`, `jeffreys`, `flat` or `wald`.
3. Press **Compute**; the table is stored as `binomial_intervals`.

## Reading the results

At 95% confidence: k = 3, n = 10 gives Wilson 0.1078 .. 0.6032, Jeffreys 0.0927 .. 0.6058, flat 0.1093 .. 0.6097, Wald 0.0160 .. 0.5840. For k = 0, n = 10 the Wald interval collapses to `0, 0`, while Wilson gives 0 .. 0.2775.

## Tips and limits

- Prefer Wilson or Jeffreys; Wald fails at k = 0, k = n and for small n.
- See [Counting statistics guide](../../guides/counting-statistics.md).
