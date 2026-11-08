## What it does

Confidence intervals for the mean of a Poisson process from observed counts (`poisson_conf_interval`).

## How to use

1. Enter the **Counts** (`0, 1, 5, 20, 100`).
2. Choose the **Interval**: `root-n`, `root-n-0`, `pearson`, `sherpagehrels`, `frequentist-confidence`, `kraft-burrows-nousek`.
3. **Sigma** (default 1) sets the width, except for `kraft-burrows-nousek`, which needs a single count, a **Background** and a **Confidence level** (e.g. `0.9`).
4. Press **Compute**; stored as `poisson_intervals`.

## Reading the results

With `frequentist-confidence` at 1 sigma: 0 counts gives 0 .. 1.841; 1 gives 0.1728 .. 3.2995; 5 gives 2.8403 .. 8.3825; 20 gives 15.566 .. 25.547; 100 gives 90.017 .. 111.033.

## Tips and limits

- `root-n` gives a zero-width interval for 0 counts; do not use it for small counts.
- For counts with a known background see the Kraft, Burrows and Nousek method.
