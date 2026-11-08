## What it does

Chooses histogram bins by rule (Knuth, Scott, Freedman, Bayesian blocks) or from fixed bins, and reports the counts.

## How to use

1. **Data** source, **Binning**: `knuth`, `scott`, `freedman`, `blocks`, `number` (**Number of bins**), `edges` (**Bin edges**). **Range** `lo, hi` is optional.
2. Press **Compute**. **Bins** lists `left, right, width, count`; **Summary** states the rule and the bin width; **Histogram** plots it.

## Reading the results

550 values with `knuth`: 10 equal bins of width 0.85204876, counts 3, 21, 74, 158, 98, 38, 8, 34, 85, 31 (two populations). `blocks` returns unequal bins.

## Tips and limits

- Knuth, Scott and Freedman give equal bins; Bayesian blocks adapt to structure.
- See [Histograms guide](../../guides/histograms-and-blocks.md).
