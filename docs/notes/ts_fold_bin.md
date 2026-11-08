## What it does

Folds a series on a period (`TimeSeries.fold`) and bins it in time (`aggregate_downsample`).

## How to use

1. Choose the **Series**, **Signal column** and **Error column**.
2. **Fold**: **Fold period** (`3.7 day`), **Epoch time** (phase zero, blank = first sample), **Epoch phase**, **Wrap phase**, **Normalise phase** (cycles in [-0.5, 0.5)). Stored as **Folded name** (default `folded`).
3. **Bin (aggregate_downsample)**: **Bin size** (`1 day`), **Bin start**, **Bin end**, **n bins** (0 = from bin size), **Aggregate** (`mean`, `median`, `sum`, `min`, `max`, `std`). Stored as **Binned name** (default `binned`).

## Reading the results

Folding on the right period gives a clean curve: phase runs over `-1.8 .. 1.8` days for a 3.7 d period. **Table** lists time (phase) and flux, **Plot** draws the folded curve.

## Tips and limits

- Without **Normalise phase** the time axis is in days from the epoch.
- A wrong period smears the fold into noise; find the period first with [Lomb-Scargle](ts_lombscargle.md) or [BLS](ts_bls.md).
