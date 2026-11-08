## What it does

Kuiper test for uniformity of phases, or for equality of two samples.

## How to use

1. **Data / phases** are the values. **Period** (default 1) folds them: `(x / period) mod 1`; with 1 the data are already phases.
2. Optional **Second sample (optional)** gives the two-sample test.
3. Press **Run Kuiper test**.

## Reading the results

The output reads `Kuiper test, one-sample (uniform)`, `V statistic = ...`, `false-positive probability = ...`, `sample size = ...`. For 100 uniform random phases: V = 0.0791, probability 0.971. A small probability rejects uniformity.

## Tips and limits

- The Kuiper test is as sensitive to a shift of the distribution as to a change in its spread, unlike Kolmogorov-Smirnov.
- Needs at least 2 finite values.
