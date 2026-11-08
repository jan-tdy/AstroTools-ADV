## What it does

Iteratively rejects outliers with `sigma_clip`, `SigmaClip` and `sigma_clipped_stats`.

## How to use

1. Choose the **Data** source.
2. **Sigma lower** and **Sigma upper** (default 3) set the bounds relative to the centre. **Max iterations** (5; 0 = until convergence), **Center function** (`median` or `mean`), **Deviation function** (`std` or `mad_std`).
3. Optional **Grow radius** (also clip neighbours) and **Axis** (N-D data), **Std ddof**.
4. Press **Compute**; **Store clipped data in workspace** keeps the masked array.

## Reading the results

For 203 values (a Gaussian near 100 plus outliers): `clipped: 4`, bounds 85.03890122 .. 115.22234711; clipped mean 100.159, median 100.131, std 5.031; unclipped mean 100.607, std 9.434. The clipped statistics describe the main population.

## Tips and limits

- A symmetric 3-sigma clip on a clean Gaussian removes about 0.3% of points.
- `mad_std` makes the bounds resistant to the outliers themselves.
- See [Outliers guide](../../guides/outliers-and-robust-stats.md).
