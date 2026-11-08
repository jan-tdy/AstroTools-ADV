---
title: Counting statistics
order: 41
lede: Confidence intervals for Poisson counts and binomial fractions, including the cases where the textbook formula fails.
---

## Poisson counts

[Poisson Intervals](../reference/analysis/stats_poisson.md): **Counts** `0 1 5 20 100`, **Interval** `frequentist-confidence`, press **Compute**.

![Poisson intervals](../assets/guides/analysis-stats-poisson.png "One-sigma intervals for small counts.")

| counts | lower | upper |
|---|---|---|
| 0 | 0 | 1.841 |
| 1 | 0.173 | 3.300 |
| 5 | 2.840 | 8.382 |
| 20 | 15.566 | 25.547 |
| 100 | 90.017 | 111.033 |

Zero counts do not mean the mean is zero: it can be up to 1.84 at one sigma. The naive `sqrt(n)` interval would give zero width there.

## A binomial fraction

[Binomial Intervals](../reference/analysis/stats_binomial.md): **k** `0, 3, 10, 50`, **n** `10, 10, 20, 100`, **Confidence level** `0.95`.

![Binomial intervals](../assets/guides/analysis-stats-binomial.png "All four interval methods.")

For 3 of 10 the methods agree roughly: Wilson `0.108 .. 0.603`, Jeffreys `0.093 .. 0.606`. For 0 of 10 the Wald interval collapses to `0 .. 0` while Wilson gives `0 .. 0.278`. Use Wilson or Jeffreys.

## A fraction that depends on x

[Binned Binomial Proportion](../reference/analysis/stats_binned_binomial.md) turns individual 0/1 outcomes into a curve. With 5 bins:

![Binned binomial](../assets/guides/analysis-stats-binned-binomial.png "Detection fraction versus x with asymmetric errors.")

The fraction rises from `0.138` (bin centre 1.02) through `0.434` (5.00) to `0.948` (8.99), each with its own asymmetric error. This is how you present a detection efficiency or a completeness curve.
